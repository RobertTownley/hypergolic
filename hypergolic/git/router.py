import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hypergolic.git.actions import (
    get_git_branches,
    git_checkout,
    git_create_branch,
    git_discard,
    git_stage,
    git_unstage,
)
from hypergolic.git.commands import GitCommandError
from hypergolic.git.diff import get_git_diff
from hypergolic.git.log import get_git_commit_detail, get_git_log
from hypergolic.git.status import get_git_status
from hypergolic.git.schemas import (
    GitBranchesResponse,
    GitChangesResponse,
    GitStatusResponse,
    GitDiffResponse,
    GitLogResponse,
    GitCommitDetailResponse,
    GitReviewResponse,
)
from hypergolic.git.commands import run_git_command
from hypergolic.git.changes import get_git_changes
from hypergolic.git.review import ReviewView, get_candidate_review, get_git_review
from hypergolic.sessions.repo_resolver import (
    RepoScope,
    available_repos,
    resolve_scoped_host_repo_and_base,
    resolve_scoped_repo_and_base,
    resolve_repo_path,
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

router = APIRouter(prefix="/api/git", tags=["git"])


def _error_detail(e: GitCommandError) -> str:
    parts = [p for p in (e.stdout, e.stderr) if p]
    return "\n".join(parts) or f"git {e.command} failed (exit {e.returncode})"


@contextmanager
def _git_errors_as_422() -> Iterator[None]:
    try:
        yield
    except GitCommandError as e:
        raise HTTPException(status_code=422, detail=_error_detail(e)) from e


class GitDiffRequest(BaseModel):
    path: str | None = None
    staged: bool = False
    # When True, diff against the session's base branch (the "All changes"
    # view) instead of the working tree / index.
    base: bool = False


class GitPathsRequest(BaseModel):
    paths: list[str]


def _scoped_repo(session_id: str, repo_scope: RepoScope) -> Path:
    return resolve_scoped_repo_and_base(session_id, repo_scope)[0]


# Every scoped git endpoint takes a required ``session_id`` (the frontend's
# only scope primitive after the Step 3 collapse) and stamps it into the
# response so the reducer can route responses back to the right per-session
# slot in workspaceSlice.bySession. ``project_id`` is gone from this router;
# sessions carry their project_id already, and the resolver reads it from
# the session row.


@router.get("/status", response_model=GitStatusResponse)
def get_git_status_endpoint(
    session_id: str, mode: Literal["all", "uncommitted"] = "uncommitted",
    repo_scope: RepoScope = "app",
):
    repo, base_branch = resolve_scoped_repo_and_base(session_id, repo_scope)
    return get_git_status(
        repo=repo, session_id=session_id,
        base_branch=base_branch if mode == "all" else None,
    )


@router.post("/diff", response_model=GitDiffResponse)
def get_git_diff_endpoint(
    req: GitDiffRequest, session_id: str, repo_scope: RepoScope = "app",
):
    repo, base_branch = resolve_scoped_repo_and_base(session_id, repo_scope)
    return get_git_diff(
        req.path, req.staged,
        repo=repo, session_id=session_id,
        base_branch=base_branch if req.base else None,
    )


@router.post("/stage")
def git_stage_endpoint(
    req: GitPathsRequest, session_id: str, repo_scope: RepoScope = "app",
):
    with _git_errors_as_422():
        git_stage(req.paths, repo=_scoped_repo(session_id, repo_scope))
    return {"status": "ok", "session_id": session_id}


@router.post("/unstage")
def git_unstage_endpoint(
    req: GitPathsRequest, session_id: str, repo_scope: RepoScope = "app",
):
    with _git_errors_as_422():
        git_unstage(req.paths, repo=_scoped_repo(session_id, repo_scope))
    return {"status": "ok", "session_id": session_id}


@router.post("/discard")
def git_discard_endpoint(
    req: GitPathsRequest, session_id: str, repo_scope: RepoScope = "app",
):
    with _git_errors_as_422():
        git_discard(req.paths, repo=_scoped_repo(session_id, repo_scope))
    return {"status": "ok", "session_id": session_id}


class GitCheckoutRequest(BaseModel):
    branch: str


@router.get("/branches", response_model=GitBranchesResponse)
def get_git_branches_endpoint(session_id: str):
    return get_git_branches(
        repo=resolve_repo_path(session_id), session_id=session_id
    )


@router.post("/checkout", response_model=GitStatusResponse)
def git_checkout_endpoint(req: GitCheckoutRequest, session_id: str):
    repo = resolve_repo_path(session_id)
    with _git_errors_as_422():
        git_checkout(req.branch, repo=repo)
    return get_git_status(repo=repo, session_id=session_id)


class GitCreateBranchRequest(BaseModel):
    name: str


@router.post("/branch", response_model=GitStatusResponse)
def git_create_branch_endpoint(req: GitCreateBranchRequest, session_id: str):
    repo = resolve_repo_path(session_id)
    with _git_errors_as_422():
        git_create_branch(req.name, repo=repo)
    return get_git_status(repo=repo, session_id=session_id)


@router.get("/changes", response_model=GitChangesResponse)
def get_git_changes_endpoint(
    session_id: str, mode: Literal["all", "uncommitted"] = "uncommitted",
    repo_scope: RepoScope = "app",
):
    repo, base_branch = resolve_scoped_repo_and_base(session_id, repo_scope)
    return get_git_changes(repo, mode, base_branch, session_id=session_id)


@router.get("/review", response_model=GitReviewResponse)
def get_git_review_endpoint(
    session_id: str, repo_scope: RepoScope = "app",
    head: str | None = None, base: str | None = None, branch: str | None = None,
    view: ReviewView = "merge",
):
    if head and base:
        if not (_SHA_RE.fullmatch(head) and _SHA_RE.fullmatch(base)):
            raise HTTPException(status_code=400, detail="head/base must be 40-hex shas")
        if branch and run_git_command("check-ref-format", "--branch", branch).returncode:
            raise HTTPException(status_code=400, detail="branch must be a valid branch name")
        host_repo, base_branch = resolve_scoped_host_repo_and_base(session_id, repo_scope)
        return get_candidate_review(
            host_repo, base, head, branch or base_branch,
            session_id=session_id, root_branch=base_branch, view=view,
        )
    repo, base_branch = resolve_scoped_repo_and_base(session_id, repo_scope)
    if base_branch is None:
        raise HTTPException(
            status_code=409,
            detail="This repo scope has no base branch to review against",
        )
    branch = run_git_command("rev-parse", "--abbrev-ref", "HEAD", cwd=repo).stdout.strip()
    return get_git_review(repo, base_branch, branch, session_id=session_id)


@router.get("/log", response_model=GitLogResponse)
def get_git_log_endpoint(
    session_id: str, count: int = 50, repo_scope: RepoScope = "app",
):
    return get_git_log(
        count, repo=_scoped_repo(session_id, repo_scope),
        session_id=session_id,
    )


@router.get("/show/{commit_hash}", response_model=GitCommitDetailResponse)
def get_git_commit_detail_endpoint(
    commit_hash: str, session_id: str, repo_scope: RepoScope = "app",
):
    return get_git_commit_detail(
        commit_hash,
        repo=_scoped_repo(session_id, repo_scope),
        session_id=session_id,
    )


@router.get("/repos")
def get_available_repos_endpoint(session_id: str):
    """Which repo scopes (app/harness/shared) exist for this session."""
    return {"session_id": session_id, "repos": available_repos(session_id)}
