from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import HTTPException

from hypergolic.sessions import session_rows
from hypergolic.git.harness_repo import harness_base_branch, harness_workspace_path
from hypergolic.sandbox.shared import session_shared_workspace, shared_dir

from hypergolic.db.models import DBSession
from hypergolic.harness.app.state import get_app


def _load_session(session_id: str) -> DBSession:
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    session_row = session_rows.fetch(session_id)
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_row


def _repo_path_for(session_row: DBSession) -> Path:
    if (
        session_row.worktree_path
        and session_row.worktree_status == "ready"
        and Path(session_row.worktree_path).exists()
    ):
        return Path(session_row.worktree_path)


    try:
        project = get_app().get_project(session_row.project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    return Path(project.path)


def resolve_repo_path(session_id: str) -> Path:
    return _repo_path_for(_load_session(session_id))


def resolve_repo_and_base(session_id: str) -> tuple[Path, str]:
    session_row = _load_session(session_id)
    path = _repo_path_for(session_row)
    live = str(path) == (session_row.worktree_path or "")
    base = session_row.base_branch
    return path, f"origin/{base}" if live else base


def resolve_project_sandbox(session_id: str):
    session_row = _load_session(session_id)
    try:
        project = get_app().get_project(session_row.project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.resolved_sandbox


RepoScope = Literal["app", "harness", "shared"]


def resolve_scoped_repo_and_base(
    session_id: str, repo: RepoScope,
) -> tuple[Path, str | None]:
    if repo == "app":
        return resolve_repo_and_base(session_id)
    if repo == "harness":
        path = harness_workspace_path(session_id)
        if not (path / ".git").exists():
            raise HTTPException(status_code=409, detail="Session has no harness clone")
        base = harness_base_branch()
        return path, f"origin/{base}" if base else None
    path = session_shared_workspace(session_id)
    if not (path / ".git").exists():
        raise HTTPException(status_code=409, detail="Session has no /shared clone")
    return path, "origin/main"


def resolve_scoped_host_repo_and_base(
    session_id: str, repo: RepoScope,
) -> tuple[Path, str]:
    session_row = _load_session(session_id)
    if repo == "harness":
        import hypergolic.config.settings as config

        base = harness_base_branch()
        if base is None:
            raise HTTPException(status_code=409, detail="No usable harness repo")
        return config.HARNESS_DIR, base
    try:
        project = get_app().get_project(session_row.project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    if repo == "shared":
        return shared_dir(project.id), "main"
    return Path(project.path), session_row.base_branch


def available_repos(session_id: str) -> dict[RepoScope, bool]:
    return {
        "app": True,
        "harness": (harness_workspace_path(session_id) / ".git").exists(),
        "shared": (session_shared_workspace(session_id) / ".git").exists(),
    }
