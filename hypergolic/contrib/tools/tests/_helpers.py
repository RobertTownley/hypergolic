from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from hypergolic.enums import SessionStatus
from hypergolic.git.sandbox_repo import hypergolic_ref
from hypergolic.schemas import Session
from tests._factories import build_session
from tests.conftest import make_project, make_session
from tests.helpers.git import clone_workspace, commit_file, run_git


def setup_clone_session(
    repo: Path, session_id: str, *, project_id: str = "proj",
) -> tuple[Session, Path]:
    make_project(project_id, "P", str(repo))
    branch = f"main-{session_id}"
    ws = repo.parent / f"ws-{session_id}"
    clone_workspace(repo, ws, branch)
    session = build_session(
        sid=session_id,
        project_id=project_id,
        project_path=str(repo),
        worktree_path=str(ws),
        worktree_branch=branch,
        base_branch="main",
    )
    return session, ws


def seed_parent_and_child(
    *,
    parent_id: str,
    child_id: str,
    project_path: Path,
    branch: str,
    project_id: str,
    child_role: str = "generalist",
) -> None:
    make_project(project_id, "P", str(project_path))
    make_session(project_id, parent_id)
    make_session(project_id, child_id, parent_id=parent_id, status=SessionStatus.CONCLUDED.value,
                 worktree_branch=branch, base_branch=f"main-{parent_id}", role=child_role)


def make_parent_session(parent_id: str, repo: Path, *, project_id: str, **overrides) -> Session:
    ws = repo.parent / f"ws-{parent_id}"
    if not ws.exists():
        clone_workspace(repo, ws, f"main-{parent_id}")
    kwargs: dict[str, Any] = dict(
        worktree_path=str(ws), worktree_branch=f"main-{parent_id}",
        base_branch="main",
    )
    kwargs.update(overrides)
    return build_session(
        sid=parent_id, project_id=project_id, project_path=str(repo), **kwargs,
    )


def committed_child_branch(
    repo: Path,
    *,
    session_id: str,
    project_id: str,
    name: str = "new.txt",
    content: str = "hi",
) -> str:
    branch = f"main-{session_id}"
    ws = repo.parent / f"child-{session_id}"
    clone_workspace(repo, ws, branch)
    commit_file(ws, name, content, "child work")
    run_git(
        repo, "fetch", "--quiet", str(ws),
        f"+refs/heads/{branch}:{hypergolic_ref(project_id, branch)}",
    )
    shutil.rmtree(ws)
    return branch


