"""Sync git state between GitHub, the host repo, and the session sandbox.

The sandbox fetches only from the host repo's gitdir, so GitHub-only state
(PR branches, moved main) is invisible until the host fetches it. `git_fetch`
hydrates the host repo (fetch-only, safe); a land push to a same-named branch
then roots the host branch at the fetched ref. `pull_request` is the way back.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field

from hypergolic.git.commands import async_run_git_command
from hypergolic.harness.primitives import InputSchema, Tool, ToolContext, ToolResult
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.eval_behavior import always_conduct
from hypergolic.commands.argv import positional


class GitFetchInput(InputSchema):
    pr: int | None = Field(
        default=None,
        description="Also fetch this PR's head to refs/remotes/pr/<n>",
    )


async def _run_git_fetch(inp: GitFetchInput, ctx: ToolContext) -> ToolResult:
    cwd = Path(ctx.session.project_path)
    args = ["fetch", "--prune", "origin"]
    if inp.pr is not None:
        # An explicit refspec replaces origin's configured one; keep heads too.
        args += ["+refs/heads/*:refs/remotes/origin/*",
                 f"+refs/pull/{inp.pr}/head:refs/remotes/pr/{inp.pr}"]
    result = await async_run_git_command(*args, cwd=cwd)
    if result.returncode != 0:
        return ToolResult.text(is_error=True, text=f"Host fetch failed:\n{result.stderr.strip()}")
    note = f" PR head at `refs/remotes/pr/{inp.pr}`." if inp.pr is not None else ""
    return ToolResult.text(
        f"Host repo fetched from its origin.{note} Remote-tracking refs are "
        "not under refs/heads, so from the sandbox fetch them explicitly, "
        "e.g. `git fetch origin refs/remotes/origin/<b>:<local>`. Landing on "
        "`HEAD:<b>` roots the host branch at GitHub's `<b>` when no local one exists."
    )


git_fetch_tool = Tool(
    id="git_fetch",
    name="Git Fetch (host)",
    description=(
        "Fetch GitHub state into the host repo so the sandbox can see remote "
        "branches / PR heads. Fetch-only; never touches worktrees or local branches"
    ),
    tags=[
        "fetch", "hydrate", "remote", "github", "pr-branch", "pull",
        "sync", "origin", "unknown-ref", "checkout-pr",
    ],
    input_schema=GitFetchInput,
    argv=positional(values={"pr"}),
    usage="git_fetch [--pr N]",
    run=_run_git_fetch,
    approval=always("ALLOW"),
    eval_behavior=always_conduct,
    timeout=300,
    requires_worktree=True,
)


__all__ = ["git_fetch_tool"]
