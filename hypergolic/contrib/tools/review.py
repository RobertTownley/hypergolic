"""Dispatch a reviewer subagent to critique the session's in-progress work.

The ``review`` tool assembles a compact review request — commit log,
diffstat, optional caller-supplied context, and the diff itself only when
small — then dispatches a ``reviewer``-role subagent. ``repo`` selects which
of the session's repos is reviewed:

- ``app`` (default): the session branch vs its base. The reviewer's own
  worktree is cut from this branch's tip, so large diffs are fetched on
  demand instead of inlined into every turn's context.
- ``harness``: the /harness clone's session branch vs the harness main.
  Those commits exist only in this session's sandbox, so the diff must fit
  inline (the reviewer's own /harness clone sits at the base for context).
- ``shared``: commits made to the project's persistent /shared repo since
  this session started. It has no branches; the reviewer reads the very
  same repo at /shared.

Validation (all run before dispatch, so a bad review attempt never creates
a child session):

- The current session must have a workspace and a base branch.
- The selected worktree must be clean (checked inside the sandbox) — the
  reviewer needs to see committed work; in-progress merges are rejected too.
- There must be at least one commit to review.
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from pathlib import Path
from typing import Literal

from pydantic import Field

from hypergolic.contrib.tools.diff_format import (
    EXCLUDED_NOTE,
    EXCLUDED_PATHSPECS,
    MAX_INLINE_DIFF_CHARS,
    fetch_diff_instruction,
)
from hypergolic.contrib.tools.dispatch import DISPATCH_PROMPT
from hypergolic.git.commands import git_checked
from hypergolic.git.harness_repo import (
    harness_base_branch,
    harness_session_branch,
    harness_workspace_path,
)
from hypergolic.harness.app.state import get_app
from hypergolic.tools import guaranteed_output
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.sandbox.shared import session_shared_workspace
from hypergolic.commands.argv import positional

logger = logging.getLogger(__name__)

REVIEW_REQUEST_HEADER = (
    "Review the committed work on this branch against its base."
)

ReviewRepo = Literal["app", "harness", "shared"]

_WORKDIRS: dict[ReviewRepo, str] = {
    "app": "/app", "harness": "/harness", "shared": "/shared",
}


class ReviewInput(InputSchema):
    context: str = Field(
        default="",
        description=(
            "Intent + focus areas; the reviewer sees only commits + diff"
        ),
    )
    repo: ReviewRepo = Field(
        default="app",
        description=(
            "Which repo's committed work to review: the project work in "
            "/app (default), your /harness config edits, or your /shared "
            "commits from this session"
        ),
    )


class _ReviewNotReadyError(Exception):
    pass


_git = partial(git_checked, error=_ReviewNotReadyError)


def _tail_sections(
    context: str, commits: str, stat: str, diff: str,
    oversize_instruction: str,
) -> list[str]:
    """Context/commits/stat/diff sections shared by every repo's request.

    ``oversize_instruction`` handles a diff that is empty (only excluded
    files) or too large to inline: every repo's commits are fetchable by
    the reviewer (from origin or from a checkpoint ref), so nothing here
    is a hard failure.
    """
    sections = []
    if context.strip():
        sections.append(f"## Context from the requesting agent\n\n{context.strip()}")
    sections.append(f"## Commits\n\n```\n{commits.strip()}\n```")
    sections.append(f"## Changed files\n\n```\n{stat.strip()}\n```")
    if diff.strip() and len(diff) <= MAX_INLINE_DIFF_CHARS:
        sections.append(f"## Diff\n\n{EXCLUDED_NOTE}\n\n```diff\n{diff}\n```")
    else:
        sections.append(f"## Diff\n\n{oversize_instruction}")
    return sections


async def _base_rev(
    session, base_branch: str, worktree_path: Path,
) -> tuple[str, str]:
    """Revision naming the base inside the session's repo.

    The session's clone has no local branch for its base — fetch the
    host-side base ref (branch or refs/hypergolic parent tip) into the
    clone's FETCH_HEAD first.
    """
    from hypergolic.git.parent_land import visible_base
    from hypergolic.git.sandbox_integrate import SandboxGitError, base_ref_for

    project = get_app().find_project(session.project_id)
    if project is None:
        raise _ReviewNotReadyError(f"Unknown project {session.project_id!r}.")
    if session.conducted_by:
        source_ref = f"refs/heads/{visible_base(session) or base_branch}"
        await _git(worktree_path, "fetch", "--quiet", "origin", source_ref)
        return "FETCH_HEAD", source_ref
    try:
        base_ref = await base_ref_for(session, project)
    except SandboxGitError as exc:
        raise _ReviewNotReadyError(str(exc)) from None
    await _git(worktree_path, "fetch", "--quiet", "origin", base_ref)
    return "FETCH_HEAD", base_ref


async def _build_review_request(
    *,
    session,
    base_branch: str,
    worktree_branch: str,
    worktree_path: Path,
    context: str,
) -> str:
    base_rev, base_ref = await _base_rev(session, base_branch, worktree_path)
    # The in-container checkout carries the base branch's *name*, so revs
    # are HEAD-relative; *worktree_branch* is the session's host-side label.
    span = f"{base_rev}...HEAD"
    commit_span = f"{base_rev}..HEAD"
    # What the *reviewer* runs in its own clone (cut from this branch's tip):
    # fetch the base from the host repo, then diff against HEAD.
    reader_span = "FETCH_HEAD...HEAD"
    reader_pre = f"git fetch origin {base_ref}"

    ahead = await _git(worktree_path, "rev-list", "--count", commit_span)
    if not int(ahead.strip() or 0):
        raise _ReviewNotReadyError(
            f"No commits on `{worktree_branch}` beyond `{base_branch}` yet — "
            "commit your work before requesting a review. (Committed to "
            '/harness or /shared instead? Pass `--repo harness` or `--repo shared`.)'
        )

    commits = await _git(worktree_path, "log", "--format=%h %s", commit_span)
    stat = await _git(worktree_path, "diff", "--stat", span)
    diff = await _git(worktree_path, "diff", span, "--", ".", *EXCLUDED_PATHSPECS)

    sections = [
        REVIEW_REQUEST_HEADER,
        f"- Branch: `{worktree_branch}`\n- Base: `{base_branch}`",
    ]
    sections += _tail_sections(
        context, commits, stat, diff,
        fetch_diff_instruction(
            reader_span, diff_is_empty=not diff.strip(), pre_command=reader_pre,
        ),
    )
    return "\n\n".join(sections)


async def _build_harness_request(*, session, context: str) -> str:
    base = await asyncio.to_thread(harness_base_branch)
    if base is None:
        raise _ReviewNotReadyError(
            "The harness repo is unusable (detached HEAD or no commits); "
            "there is no /harness clone to review."
        )
    path = harness_workspace_path(session.id)
    if not (path / ".git").exists():
        raise _ReviewNotReadyError("This session has no /harness clone.")
    branch = harness_session_branch(session.live_branch())

    await _git(path, "fetch", "--quiet", "origin", f"refs/heads/{base}")
    ahead = await _git(path, "rev-list", "--count", "FETCH_HEAD..HEAD")
    if not int(ahead.strip() or 0):
        raise _ReviewNotReadyError(
            f"No /harness commits on `{branch}` beyond `{base}` yet — "
            "commit your work before requesting a review."
        )

    commits = await _git(path, "log", "--format=%h %s", "FETCH_HEAD..HEAD")
    stat = await _git(path, "diff", "--stat", "FETCH_HEAD...HEAD")
    diff = await _git(path, "diff", "FETCH_HEAD...HEAD", "--", ".",
                      *EXCLUDED_PATHSPECS)

    # Checkpoint the commits so the reviewer can fetch them from its own
    # /harness clone (which sits at the harness base).
    ref = await _checkpoint_for_reviewer(session, "harness")
    sections = [
        "Review the committed Hypergolic-config work on this session's "
        "/harness branch against the harness main.",
        f"- Branch: `{branch}`\n- Base: `{base}` (the harness repo, not the "
        "project)\n- Your own /harness checkout sits at the base — read "
        "files there for surrounding context.",
    ]
    sections += _tail_sections(
        context, commits, stat, diff,
        fetch_diff_instruction(
            "HEAD...FETCH_HEAD", diff_is_empty=not diff.strip(),
            pre_command=f"cd /harness && git fetch origin {ref}",
        ),
    )
    return "\n\n".join(sections)


async def _checkpoint_for_reviewer(session, repo: str) -> str:
    from hypergolic.git.sandbox_integrate import SandboxGitError, refresh_slot_ref, slot_for

    project = get_app().find_project(session.project_id)
    assert project is not None
    try:
        return await refresh_slot_ref(
            session, project, await asyncio.to_thread(slot_for, session, project, repo),
        )
    except SandboxGitError as exc:
        raise _ReviewNotReadyError(str(exc)) from None


async def _build_shared_request(*, session, context: str) -> str:
    path = session_shared_workspace(session.id)
    if not (path / ".git").exists():
        raise _ReviewNotReadyError("This session has no /shared clone.")

    await _git(path, "fetch", "--quiet", "origin", "refs/heads/main")
    ahead = await _git(path, "rev-list", "--count", "FETCH_HEAD..HEAD")
    if not int(ahead.strip() or 0):
        raise _ReviewNotReadyError(
            "No /shared commits beyond the landed main — commit your "
            "work before requesting a review."
        )

    commits = await _git(path, "log", "--format=%h %s", "FETCH_HEAD..HEAD")
    stat = await _git(path, "diff", "--stat", "FETCH_HEAD...HEAD")
    diff = await _git(path, "diff", "FETCH_HEAD...HEAD", "--", ".",
                      *EXCLUDED_PATHSPECS)

    ref = await _checkpoint_for_reviewer(session, "shared")
    sections = [
        "Review this session's committed (not yet landed) work in the "
        "project's persistent /shared repo.",
        "- Repo: `/shared` — lands on its main via `git push origin main`\n"
        "- Your own /shared checkout sits at the landed main — read files "
        "there for surrounding context.",
    ]
    sections += _tail_sections(
        context, commits, stat, diff,
        fetch_diff_instruction(
            "HEAD...FETCH_HEAD", diff_is_empty=not diff.strip(),
            pre_command=f"cd /shared && git fetch origin {ref}",
        ),
    )
    return "\n\n".join(sections)


async def _handle_review(inp: ReviewInput, ctx: ToolContext) -> ToolResult:
    from hypergolic.dispatch.runner import dispatch
    from hypergolic.git.sandbox_integrate import SandboxGitError, assert_sandbox_worktree_clean

    session = ctx.session

    project = get_app().find_project(session.project_id)
    if project is None:
        return ToolResult.text(
            f"Unknown project {session.project_id!r}.",
            is_error=True,
        )
    try:
        await assert_sandbox_worktree_clean(
            session, project, workdir=_WORKDIRS[inp.repo],
        )
    except SandboxGitError as exc:
        return ToolResult.text(f"Cannot review a dirty worktree. {exc}", is_error=True)

    try:
        if inp.repo == "harness":
            prompt_text = await _build_harness_request(
                session=session, context=inp.context,
            )
        elif inp.repo == "shared":
            prompt_text = await _build_shared_request(
                session=session, context=inp.context,
            )
        else:
            prompt_text = await _build_review_request(
                session=session,
                base_branch=session.base_branch,
                worktree_branch=session.live_branch(),
                worktree_path=Path(session.worktree_path),
                context=inp.context,
            )
    except _ReviewNotReadyError as exc:
        return ToolResult.text(str(exc), is_error=True)

    result = await dispatch(
        parent_session_id=session.id,
        content_blocks=[{"type": "text", "text": prompt_text}],
        dispatch_prompt=DISPATCH_PROMPT,
        broadcast=ctx.broadcast,
        role="reviewer",
    )

    if result.outcome == "success":
        guaranteed_output.post(session.id, result.conclusion)
        return ToolResult.text(result.conclusion)
    return ToolResult.text(
        f"Review dispatch {result.outcome}: {result.conclusion}",
        is_error=True,
    )


ReviewTool = Tool(
    id="review",
    tags=["code-review", "critique", "feedback", "self-review", "quality", "diff"],
    name="Review",
    description=(
        "Critique committed work vs base: /app branch (default), /harness "
        "edits, or this session's /shared commits. Needs a clean worktree"
    ),
    input_schema=ReviewInput,
    argv=positional(joined="context", values={"repo"}),
    usage="review [--repo app|harness|shared] [context...]",
    run=_handle_review,
    approval=always("ALLOW"),
    requires_worktree=True,
)


__all__ = ["ReviewTool"]
