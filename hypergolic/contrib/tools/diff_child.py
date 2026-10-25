"""Dynamic diff_child tool.

Injected into a parent session when one or more of its concluded children
has a surviving worktree branch. Lets the parent see what a child's
branch changed (relative to the parent's branch) *before* deciding
whether to merge or discard via ``merge_child``.

Read-only. Runs in the parent's workspace after fetching the child's
preserved ``refs/hypergolic`` ref from the host repo.
"""
from __future__ import annotations

import logging
from typing import Any
from pathlib import Path

from hypergolic.contrib.tools.diff_format import (
    EXCLUDED_NOTE,
    EXCLUDED_PATHSPECS,
    MAX_INLINE_DIFF_CHARS,
    fetch_diff_instruction,
)
from hypergolic.contrib.tools.merge_child import (
    child_input_schema,
    describe_candidates,
    find_merge_candidates,
    pick_child,
)
from hypergolic.git.commands import async_run_git_command
from hypergolic.git.sandbox_integrate import fetch_child_ref
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.schemas import Session
from hypergolic.commands.argv import positional

logger = logging.getLogger(__name__)


def _parent_workspace(parent_session: Session) -> Path:
    assert parent_session.worktree_path, "diff_child requires the parent's workspace"
    return Path(parent_session.worktree_path)


def build_diff_child_tool(parent_session: Session) -> Tool | None:
    candidates = find_merge_candidates(parent_session.id, parent_session.worktree_branch)
    if not candidates:
        return None

    parent_branch = parent_session.worktree_branch or parent_session.base_branch
    DiffChildInput = child_input_schema(candidates)

    async def run(inp: Any, ctx: ToolContext) -> ToolResult:
        child_id, candidate = pick_child(candidates, inp.child_session_id)
        if candidate is None:
            return ToolResult.text(
                f"No eligible child with id {child_id}",
                is_error=True,
            )
        if not parent_branch:
            return ToolResult.text(
                "Parent session has no branch to diff against.",
                is_error=True,
            )

        project_path = _parent_workspace(ctx.session)
        child = await fetch_child_ref(ctx.session, candidate.worktree_branch, project_path)
        if child is None:
            return ToolResult.text(
                f"Child branch `{candidate.worktree_branch}` was not "
                "preserved on the host; nothing to diff.",
                is_error=True,
            )
        span = f"{parent_branch}...{child}"

        stat_result = await async_run_git_command(
            "diff", "--stat", span, cwd=project_path,
        )
        if stat_result.returncode != 0:
            return ToolResult.text(
                f"git diff failed:\n"
                f"{stat_result.stderr.strip() or stat_result.stdout.strip()}",
                is_error=True,
            )
        if not stat_result.stdout.strip():
            return ToolResult.text(
                f"No diff: `{candidate.worktree_branch}` has no commits "
                f"beyond `{parent_branch}`.",
            )

        diff_result = await async_run_git_command(
            "diff", span, "--", ".", *EXCLUDED_PATHSPECS, cwd=project_path,
        )
        diff = diff_result.stdout if diff_result.returncode == 0 else ""

        header = (
            f"Diff of `{candidate.worktree_branch}` against `{parent_branch}`:"
            f"\n\n```\n{stat_result.stdout.strip()}\n```"
        )
        if diff.strip() and len(diff) <= MAX_INLINE_DIFF_CHARS:
            body = f"{EXCLUDED_NOTE}\n\n```diff\n{diff}\n```"
        else:
            body = fetch_diff_instruction(span, diff_is_empty=not diff.strip())
        return ToolResult.text(f"{header}\n\n{body}")

    return Tool(
        id="diff_child",
        tags=["subagent", "child-session", "inspect", "diff"],
        name="Diff Child Branch",
        description=describe_candidates(
            "Show the diff a concluded child branch would bring if merged",
            candidates,
        ),
        input_schema=DiffChildInput,
        argv=positional("child_session_id"),
        usage="diff_child <child_session_id>",
        run=run,
        approval=always("ALLOW"),
        requires_worktree=True,
    )


__all__ = ["build_diff_child_tool"]
