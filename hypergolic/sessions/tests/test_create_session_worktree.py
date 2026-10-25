from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.timeout(10)

from hypergolic.enums import ModelTier  # noqa: E402
from hypergolic.harness.app.core import App  # noqa: E402
from hypergolic.harness.app.state import set_app  # noqa: E402
from hypergolic.harness.project import Project  # noqa: E402
from hypergolic.schemas import Session  # noqa: E402
from hypergolic.sessions import session_rows  # noqa: E402
from tests.helpers.git import run_git  # noqa: E402
from hypergolic.sessions.operations import (  # noqa: E402
    create_session,
    delete_session_tree,
)
from hypergolic.sessions.operations import load_session  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402


@pytest.fixture
def project_row(repo: Path):
    app = App()
    project = Project(id="proj-e2e", name="P", description="d", git_root=str(repo))
    app.register_project(project)
    set_app(app)
    with patch(
        "hypergolic.sandbox.manager.repo_creation.provision_session_repos",
        new=AsyncMock(),
    ):
        yield "proj-e2e"


def _wait_for_status(session_id: str, target: str, timeout: float = 5.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = session_rows.fetch(session_id)
        status = row.worktree_status if row else None
        if status == target:
            assert status is not None
            return status
        time.sleep(0.02)
    raise AssertionError(
        f"Session {session_id} did not reach worktree_status={target!r} "
        f"within {timeout}s (last status={status!r})"
    )


def _join_worktree_threads(timeout: float = 5.0) -> None:
    for thread in list(threading.enumerate()):
        if thread.name.startswith(("worktree-create-", "worktree-teardown-")):
            thread.join(timeout=timeout)


def test_create_session_with_main_base(
    repo: Path, worktrees_home: Path, project_row: str,
) -> None:
    session = create_session(
        project_id=project_row, base_branch="main", model_tier=ModelTier.MEDIUM,
    )
    assert session.worktree_path is not None
    assert session.worktree_branch is not None
    assert session.base_branch == "main"
    assert session.worktree_branch == f"main-{session.id}"
    assert session.working_directory() == Path(session.worktree_path)
    assert Path(session.worktree_path).is_relative_to(worktrees_home / project_row)

    _wait_for_status(session.id, "ready")
    assert Path(session.worktree_path).exists()


def test_create_session_with_explicit_base_branch(
    repo: Path, worktrees_home: Path, project_row: str,
) -> None:
    run_git(repo, "branch", "feature/x")
    session = create_session(
        project_id=project_row,
        base_branch="feature/x",
        model_tier=ModelTier.MEDIUM,
    )
    assert session.base_branch == "feature/x"
    assert session.worktree_branch == f"feature/x-{session.id}"
    assert session.worktree_path is not None
    assert "feature-x-" in Path(session.worktree_path).name

    _wait_for_status(session.id, "ready")


def test_create_session_persists_worktree_fields(
    repo: Path, worktrees_home: Path, project_row: str,
) -> None:
    session = create_session(
        project_id=project_row, base_branch="main", model_tier=ModelTier.MEDIUM,
    )
    _wait_for_status(session.id, "ready")
    row = session_rows.fetch_one(session.id)
    assert (row.worktree_path, row.worktree_branch, row.base_branch, row.worktree_status) == (
        session.worktree_path, session.worktree_branch, "main", "ready")


def test_create_session_persists_origin(
    repo: Path, worktrees_home: Path, project_row: str,
) -> None:
    session = create_session(
        project_id=project_row, base_branch="main",
        model_tier=ModelTier.MEDIUM, origin="cli",
    )
    _wait_for_status(session.id, "ready")
    assert load_session(session.id).origin == "cli"


def test_delete_session_tree_removes_workspace(
    repo: Path, worktrees_home: Path, project_row: str,
) -> None:
    session: Session = create_session(
        project_id=project_row, base_branch="main", model_tier=ModelTier.MEDIUM,
    )
    assert session.worktree_path is not None
    assert session.worktree_branch is not None
    _wait_for_status(session.id, "ready")
    assert Path(session.worktree_path).exists()

    delete_session_tree(session.id)
    _join_worktree_threads()

    assert not Path(session.worktree_path).exists()


def test_create_session_provisions_in_sandbox(repo: Path, worktrees_home: Path) -> None:
    app = App()
    project = Project(id="proj-sbx", name="P", description="d", git_root=str(repo))
    app.register_project(project)
    set_app(app)

    async def fake_provision(session_obj, project_obj):
        assert project_obj.id == "proj-sbx"
        assert session_obj.worktree_path and Path(session_obj.worktree_path).is_dir()

    with patch(
        "hypergolic.sandbox.manager.repo_creation.provision_session_repos",
        side_effect=fake_provision,
    ) as provision:
        session = create_session(project_id="proj-sbx", base_branch="main")
        _wait_for_status(session.id, "ready")
    _join_worktree_threads()

    provision.assert_called_once()
    assert session.worktree_path is not None
    assert not (Path(session.worktree_path) / ".git").exists()


def test_create_session_records_repo_shas_and_pins(
    repo: Path, worktrees_home: Path, project_row: str,
) -> None:
    tip = run_git(repo, "rev-parse", "refs/heads/main").stdout.strip()
    session = create_session(
        project_id=project_row, base_branch="main",
        repo_pins={"shared": "a" * 40},
    )
    assert session.repo_pins == {"shared": "a" * 40}
    row = session_rows.fetch_one(session.id)
    assert row.repo_pins == {"shared": "a" * 40}
    assert row.repo_shas is not None and (row.repo_shas["app"], row.repo_shas["shared"]) == (tip, "a" * 40)
    assert load_session(session.id).repo_pins == {"shared": "a" * 40}
    _join_worktree_threads()


def test_create_session_rejects_unknown_pin_slot(
    repo: Path, worktrees_home: Path, project_row: str,
) -> None:
    with pytest.raises(ValueError, match="Unknown repo slot"):
        create_session(
            project_id=project_row, base_branch="main",
            repo_pins={"appp": "b" * 40},
        )
