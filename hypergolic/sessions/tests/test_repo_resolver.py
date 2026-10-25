from pathlib import Path

import pytest
from fastapi import HTTPException

from hypergolic.sessions import session_rows
from hypergolic.sessions.repo_resolver import resolve_repo_path
from tests.conftest import make_project, make_session

def test_empty_session_id_raises_400():
    with pytest.raises(HTTPException) as exc:
        resolve_repo_path("")
    assert exc.value.status_code == 400
    assert "session_id" in exc.value.detail.lower()


def test_resolves_session_worktree_when_ready(tmp_path):
    make_project(pid="p1", path="/tmp/base")
    wt = tmp_path / "wt"
    wt.mkdir()
    sid = make_session(
        project_id="p1",
        worktree_path=str(wt),
        worktree_branch="feat",
        base_branch="main",
    )

    assert resolve_repo_path(sid) == wt


def test_falls_back_to_project_path_when_worktree_not_ready(tmp_path):
    make_project(pid="p1", path="/tmp/base")
    wt = tmp_path / "wt"
    wt.mkdir()
    sid = make_session(
        project_id="p1",
        worktree_path=str(wt),
        base_branch="main",
    )
    session_rows.update(sid, worktree_status="creating")

    assert resolve_repo_path(sid) == Path("/tmp/base")


def test_falls_back_when_worktree_dir_missing(tmp_path):
    make_project(pid="p1", path="/tmp/base")
    sid = make_session(
        project_id="p1",
        worktree_path=str(tmp_path / "does-not-exist"),
        base_branch="main",
    )

    assert resolve_repo_path(sid) == Path("/tmp/base")


def test_falls_back_to_project_when_session_has_no_worktree():
    make_project(pid="p1", path="/tmp/base")
    sid = make_session(project_id="p1")
    assert resolve_repo_path(sid) == Path("/tmp/base")


def test_missing_session_raises_404():
    with pytest.raises(HTTPException) as exc:
        resolve_repo_path("no-such-session")
    assert exc.value.status_code == 404
    assert "session" in exc.value.detail.lower()

