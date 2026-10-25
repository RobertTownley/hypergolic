from __future__ import annotations

import asyncio
import logging
from typing import Any
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from hypergolic.sessions import session_rows
from hypergolic.git.commands import async_run_git_command
from hypergolic.git.sandbox_integrate import (
    SandboxGitError,
    assert_sandbox_worktree_clean,
    fetch_child_ref,
)
from hypergolic.git.parent_land import PARENT_PIN_PREFIX
from hypergolic.git.sandbox_repo import delete_hypergolic_ref
from hypergolic.harness.app.state import get_app
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.schemas import Session
from hypergolic.sessions.operations import clear_session_worktree_fields
from hypergolic.enums import SessionStatus
from hypergolic.commands.argv import positional

logger = logging.getLogger(__name__)


class MergeCandidate(BaseModel):
    session_id: str
    worktree_branch: str
    description: str | None = None
    conclusion_feedback: str | None = None


def find_merge_candidates(
    parent_session_id: str, parent_branch: str | None = None,
) -> list[MergeCandidate]:
    return [
        MergeCandidate(
            session_id=r.id,
            worktree_branch=r.worktree_branch or "",
            description=r.description,
            conclusion_feedback=r.conclusion_feedback,
        )
        for r in session_rows.find(parent_id=parent_session_id)
        if r.status == SessionStatus.CONCLUDED and r.role != "reviewer"
        and r.worktree_branch and (
            parent_branch is None
            or r.base_branch == parent_branch
            or (r.base_branch or "").startswith(PARENT_PIN_PREFIX)
        )
    ]


def describe_candidates(summary: str, candidates: list[MergeCandidate]) -> str:
    lines = [summary, "", "Eligible children:"]
    for c in candidates:
        label = c.description or c.session_id
        lines.append(f"- `{c.session_id}` (branch `{c.worktree_branch}`): {label}")
    return "\n".join(lines)


def child_input_schema(candidates: list[MergeCandidate]) -> Any:
    SessionIdEnum = Enum(  # type: ignore[misc]
        "SessionIdEnum",
        {c.session_id: c.session_id for c in candidates},
        type=str,
    )

    class ChildInput(InputSchema):
        child_session_id: SessionIdEnum  # type: ignore[valid-type]

    return ChildInput


def pick_child(
    candidates: list[MergeCandidate], raw: object,
) -> tuple[str, MergeCandidate | None]:
    child_id = raw.value if isinstance(raw, Enum) else str(raw)
    return child_id, next((c for c in candidates if c.session_id == child_id), None)


def build_merge_child_tool(parent_session: Session) -> Tool | None:
    candidates = find_merge_candidates(parent_session.id, parent_session.worktree_branch)
    if not candidates:
        return None

    class MergeChildInput(child_input_schema(candidates)):
        commit_message: str = Field(
            default="",
            description=(
                "Squash commit message; required unless `discard`"
            ),
        )
        discard: bool = Field(
            default=False,
            description="Delete the child's branch without merging",
        )

    async def run(inp: MergeChildInput, ctx: ToolContext) -> ToolResult:
        child_id, candidate = pick_child(candidates, inp.child_session_id)
        if candidate is None:
            return ToolResult.text(
                f"No merge-eligible child with id {child_id}",
                is_error=True,
            )
        return await _run(
            parent_session=ctx.session,
            candidate=candidate,
            commit_message=inp.commit_message,
            discard=inp.discard,
        )

    return Tool(
        id="merge_child",
        tags=["subagent", "child-session", "integrate", "merge"],
        name="Merge Child Branch",
        description=describe_candidates(
            "Squash-merge a concluded child's branch into your own, or discard it",
            candidates,
        ),
        input_schema=MergeChildInput,
        argv=positional(
            "child_session_id", joined="commit_message", bools={"discard"},
        ),
        usage="merge_child <child_session_id> <commit message...> [--discard]",
        run=run,
        approval=always("ALLOW"),
        requires_worktree=True,
    )


def _parent_workspace(parent_session: Session) -> Path:
    assert parent_session.worktree_path, "merge_child requires the parent's workspace"
    return Path(parent_session.worktree_path)


def _error(text: str) -> ToolResult:
    return ToolResult.text(text, is_error=True)


async def _merge_precheck(
    parent_session: Session, commit_message: str
) -> ToolResult | None:
    if not commit_message.strip():
        return _error("`commit_message` is required unless `discard` is true.")
    project = get_app().find_project(parent_session.project_id)
    if project is None:
        return _error(f"Unknown project {parent_session.project_id!r}; cannot merge.")
    try:
        await assert_sandbox_worktree_clean(parent_session, project)
    except SandboxGitError as exc:
        return _error(
            "Cannot squash-merge into a dirty worktree — commit "
            f"or discard your in-flight changes first. {exc}"
        )
    return None


async def _squash_commit(
    merge_source: str, commit_message: str, project_path: Path
) -> ToolResult | None:
    squash = await async_run_git_command(
        "merge", "--squash", merge_source, cwd=project_path,
    )
    if squash.returncode != 0:
        await async_run_git_command("merge", "--abort", cwd=project_path)
        return _error(
            f"git merge --squash {merge_source} failed:\n"
            f"{squash.stderr.strip() or squash.stdout.strip()}"
        )
    commit = await async_run_git_command(
        "commit", "-m", commit_message, cwd=project_path,
    )
    if commit.returncode != 0:
        return _error(
            "Squash staged, but commit failed:\n"
            f"{commit.stderr.strip() or commit.stdout.strip()}"
        )
    return None


async def _cleanup_merged(
    parent_session: Session,
    candidate: MergeCandidate,
    merge_source: str,
    project_path: Path,
) -> None:
    await async_run_git_command("update-ref", "-d", merge_source, cwd=project_path)
    await _delete_host_child_ref(parent_session, candidate.worktree_branch)
    await asyncio.to_thread(clear_session_worktree_fields, candidate.session_id, clear_branch=True)


async def _run(
    *,
    parent_session: Session,
    candidate: MergeCandidate,
    commit_message: str,
    discard: bool,
) -> ToolResult:
    project_path = _parent_workspace(parent_session)
    branch = candidate.worktree_branch

    if discard:
        await _delete_host_child_ref(parent_session, branch)
        clear_session_worktree_fields(candidate.session_id, clear_branch=True)
        return ToolResult.text(f"Discarded branch `{branch}` without merging.")

    precheck = await _merge_precheck(parent_session, commit_message)
    if precheck is not None:
        return precheck

    merge_source = await fetch_child_ref(parent_session, branch, project_path)
    if merge_source is None:
        return _error(
            f"Child branch `{branch}` was not preserved on the host; "
            "nothing to merge."
        )

    failure = await _squash_commit(merge_source, commit_message, project_path)
    if failure is not None:
        return failure

    await _cleanup_merged(parent_session, candidate, merge_source, project_path)
    return ToolResult.text(f"Squash-merged `{branch}` and cleaned up the branch.")


async def _delete_host_child_ref(parent_session: Session, branch: str) -> None:
    await asyncio.to_thread(
        delete_hypergolic_ref,
        parent_session.project_path, parent_session.project_id, branch,
    )


__all__ = [
    "MergeCandidate",
    "build_merge_child_tool",
    "find_merge_candidates",
]
