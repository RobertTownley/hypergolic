"""Broker side of `git push origin HEAD:<branch>`: gate, then land.

The quarantine's update hook invokes this command with the pushed branch name
and sha; the command validates the request against the *host* repo (never
trusting the quarantine), builds the merge candidate (a squash commit, or the pushed sha itself in
fast-forward mode), runs the repo's gate pipeline, and advances the branch. Its stdout/stderr stream back over the
push connection as ``remote:`` lines, and its exit code accepts or rejects
the pushed ref. Invoking it by hand is equivalent to pushing.

The branch resolves like ``git checkout <name>``: an existing host branch;
else a same-named branch on GitHub (visible after ``git_fetch``), tracked;
else a new branch rooted where the pushed work forked from the session's
base. Nothing is created until the gates pass.

A dispatched child's push to its base (the parent's session branch, or the
parent's own base name the child sees) lands in the parent's sandbox instead
(:mod:`hypergolic.git.parent_land`): fresh parent checkpoint as the target,
the same gates, then a fast-forward inside the parent's container.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import replace

from hypergolic.commands.argv import positional
from hypergolic.contrib.tools.land.inputs import LandInput, LandRejected
from hypergolic.contrib.tools.land.pipeline import land
from hypergolic.gates.candidate import CandidateError
from hypergolic.gates.model import SandboxRepo
from hypergolic.git.commands import async_run_git_command
from hypergolic.git.parent_land import land_parent
from hypergolic.git.sandbox_integrate import SandboxGitError, slot_for
from hypergolic.harness.app.state import get_app
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import CommandResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.telemetry.events import emit
from hypergolic.tools import guaranteed_output

logger = logging.getLogger(__name__)

_SHA = re.compile(r"^[0-9a-f]{40}$")


async def _handle_land(inp: LandInput, ctx: ToolContext) -> CommandResult:
    session = ctx.session
    project = get_app().find_project(session.project_id)
    if project is None:
        return CommandResult.fail(f"unknown project {session.project_id!r}")
    if not _SHA.match(inp.sha):
        return CommandResult.fail(f"not a commit sha: {inp.sha!r}")
    valid = await async_run_git_command("check-ref-format", "--branch", inp.branch)
    if valid.returncode != 0:
        return CommandResult.fail(f"rejected: not a valid branch name: {inp.branch!r}")
    repo = SandboxRepo(inp.repo)
    parent = None
    if repo is SandboxRepo.APP:
        parent = await asyncio.to_thread(land_parent, session, inp.branch)
    # A child's push to its base lands in the parent's sandbox branch; the
    # slot then names that real branch, which is what the parent approves.
    branch = session.base_branch if parent is not None else inp.branch
    try:
        slot = replace(await asyncio.to_thread(slot_for, session, project, repo.value), base_branch=branch)
    except SandboxGitError as exc:
        return CommandResult.fail(f"rejected: {exc}")

    def landed(outcome: str) -> None:
        emit(
            "land.finished", session_id=session.id, outcome=outcome, repo=repo.value,
            branch=branch, to_parent=parent is not None,
        )

    try:
        verdict = await land(inp, ctx, slot, parent)
    except (CandidateError, LandRejected, SandboxGitError) as exc:
        landed("rejected")
        return CommandResult.fail(f"rejected: {exc}")
    except Exception:
        landed("error")
        logger.exception("land failed for session %s", session.id)
        return CommandResult.fail(
            "rejected: the land pipeline hit an internal error; see the "
            "server log"
        )
    out = "\n".join(verdict.lines) + "\n"
    guaranteed_output.post(session.id, out)
    landed("landed" if verdict.ok else "gate_failed")
    if verdict.ok:
        return CommandResult.ok(out)
    return CommandResult(stdout=out, stderr="rejected by the gate pipeline\n", exit_code=1)


LandTool = Tool(
    id="land",
    tags=["merge", "squash", "land", "push", "branch", "gates"],
    name="Land",
    description=(
        "Gate and squash-land a pushed commit onto a host branch. "
        "Invoked by `git push origin HEAD:<branch>` — push instead of calling this"
    ),
    input_schema=LandInput,
    argv=positional(values={"repo", "branch", "sha", "message", "description", "mode"}),
    usage="land --branch <branch> --sha <sha> [--repo app|harness|shared] [--message '...'] [--description '...'] [--mode squash|fast-forward]",
    run=_handle_land,
    approval=always("ALLOW"),
    requires_worktree=True,
)


__all__ = ["LandTool", "LandInput"]
