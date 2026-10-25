from __future__ import annotations

import asyncio

from hypergolic.contrib.tools.land.dest import Dest, host_dest, parent_dest
from hypergolic.contrib.tools.land.inputs import LandInput, LandRejected, Target
from hypergolic.contrib.tools.land.target import resolve_target
from hypergolic.gates.candidate import (
    build_candidate,
    derive_message,
    is_ancestor,
    rebase_candidate,
    tip_message,
)
from hypergolic.gates.config import gates_for
from hypergolic.gates.model import LandMode, OnStaleBase, SandboxRepo
from hypergolic.gates.request import GateVerdict, LandRequest
from hypergolic.gates.runner import run_pipeline
from hypergolic.git.commands import async_run_git_command
from hypergolic.git.parent_land import parent_tip
from hypergolic.git.quarantine import fetch_quarantine_ref
from hypergolic.git.sandbox_integrate import slot_for
from hypergolic.git.sandbox_repo import hypergolic_ref
from hypergolic.harness.app.state import get_app
from hypergolic.harness.primitives.tool import ToolContext

MAX_STALE_RETRIES = 3


async def land(inp: LandInput, ctx: ToolContext, slot, parent=None) -> GateVerdict:
    session, project = ctx.session, get_app().find_project(ctx.session.project_id)
    assert project is not None
    repo = SandboxRepo(inp.repo)
    host = slot.host_repo

    checkpoint = hypergolic_ref(slot.ref_scope, slot.session_branch)
    fetched = await fetch_quarantine_ref(
        host_repo=host, session_id=session.id, repo=slot.repo,
        src_ref=inp.sha, dst_ref=checkpoint,
    )
    if fetched.returncode != 0:
        raise LandRejected(
            f"the pushed commit never reached the quarantine:\n{fetched.stderr.strip()}"
        )

    if parent is not None:
        target = Target(await parent_tip(parent, project))
        dest = parent_dest(ctx, project, parent, inp.branch)
    else:
        root_branch = (await asyncio.to_thread(slot_for, session, project, repo.value)).base_branch
        target = await resolve_target(host, slot.base_branch, root_branch, inp.sha)
        dest = host_dest(ctx, project, slot, target)
    base_sha = target.sha
    if inp.sha == base_sha:
        raise LandRejected(f"nothing to land: the push matches `{inp.branch}`'s tip")
    if not await is_ancestor(host, base_sha, inp.sha):
        raise LandRejected(
            f"`{inp.branch}` has moved since you last fetched. "
            f"Run `{dest.pull_hint}`, resolve, commit, and push again."
        )

    mode: LandMode = inp.mode or project.land_mode
    if mode == "fast-forward":
        candidate = inp.sha
        message = inp.message.strip() or await tip_message(host, base_sha, inp.sha)
    else:
        message = inp.message.strip() or await derive_message(host, base_sha, inp.sha)
        candidate = await build_candidate(host, sha=inp.sha, base_sha=base_sha, message=message)
    candidate_ref = f"{checkpoint}-candidate-{inp.sha[:8]}"
    try:
        return await _gate_and_advance(
            ctx, slot, repo, dest, base_sha, candidate, candidate_ref, message, inp.sha, mode,
            shown=inp.branch, description=inp.description.strip(),
        )
    finally:
        await async_run_git_command("update-ref", "-d", candidate_ref, cwd=host)


async def _gate_and_advance(
    ctx: ToolContext, slot, repo: SandboxRepo, dest: Dest,
    base_sha: str, candidate: str, candidate_ref: str, message: str,
    pushed_sha: str, mode: LandMode, *, shown: str, description: str = "",
) -> GateVerdict:
    """*shown* is the branch the push named: every line the pusher reads uses it,
    so a child pushing ``main`` never sees its parent's real branch name."""
    session, project = ctx.session, get_app().find_project(ctx.session.project_id)
    assert project is not None
    host = slot.host_repo
    on_stale: OnStaleBase = (
        "reject" if mode == "fast-forward"
        else "land" if repo is SandboxRepo.HARNESS
        else project.on_stale_base
    )
    gates = gates_for(get_app(), project, repo)
    lines: list[str] = []
    if dest.blocker and (blocked := await dest.blocker(base_sha, candidate)):
        raise LandRejected(blocked)

    for _ in range(MAX_STALE_RETRIES):
        await async_run_git_command(
            "update-ref", candidate_ref, candidate, cwd=host,
        )
        verdict = await run_pipeline(gates, LandRequest(
            session=session, project=project, slot=slot, base_sha=base_sha,
            candidate=candidate, candidate_ref=candidate_ref, message=message,
            broadcast=ctx.broadcast, description=description,
        ))
        lines += verdict.lines
        if not verdict.ok:
            return GateVerdict(ok=False, lines=lines)

        ok, detail = await dest.advance(base_sha, candidate, lines)
        if ok:
            verb = "fast-forwarded" if mode == "fast-forward" else "merged into"
            lines.append(f"{verb} {shown} as {candidate[:8]}")
            await dest.post(pushed_sha, candidate)
            return GateVerdict(ok=True, lines=lines)

        new_tip = await dest.tip()
        if new_tip is None or new_tip == base_sha:
            raise LandRejected(detail)
        base_sha, candidate = await _restack(
            on_stale, host, candidate=candidate, new_tip=new_tip, message=message,
        )
        if on_stale == "land":
            gates = []  # already green; land the rebased candidate directly
        lines.append(
            f"{shown} moved while gates ran; "
            + ("landing onto the new tip" if on_stale == "land" else "re-running gates")
        )
    raise LandRejected(
        f"`{shown}` keeps moving; push again when it settles"
    )


async def _restack(
    on_stale: OnStaleBase, host, *, candidate: str, new_tip: str, message: str,
) -> tuple[str, str]:
    if on_stale == "reject":
        raise LandRejected(
            "the base moved while gates ran (this repo requires an "
            "up-to-date base). Run `git pull`, then push again."
        )
    rebased, reason = await rebase_candidate(
        host, candidate=candidate, new_tip=new_tip, message=message,
    )
    if rebased is None:
        raise LandRejected(f"{reason}. Run `git pull`, resolve, and push again.")
    return new_tip, rebased
