from __future__ import annotations

from pathlib import Path
import shutil

import pytest

pytestmark = pytest.mark.timeout(10)

from hypergolic.sessions import session_rows  # noqa: E402
from hypergolic.git.worktree import worktree_path_for, worktrees_root  # noqa: E402
from hypergolic.git import worktree_doctor  # noqa: E402
from hypergolic.git.worktree_doctor import reconcile_worktrees  # noqa: E402
from tests.conftest import make_project, make_session  # noqa: E402

import hypergolic.config.settings as settings_module  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_internals(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "INTERNALS_DIR", tmp_path / "internals")
    monkeypatch.setattr(worktree_doctor, "_reconcile_gitdir_volumes", lambda report, dry_run: None)


def _session_workspace(project_id: str, sid: str) -> Path:
    ws = worktree_path_for(project_id, f"main-{sid}")
    ws.mkdir(parents=True)
    make_session(project_id, sid, worktree_path=str(ws), worktree_branch=f"main-{sid}")
    return ws


def test_reconcile_is_noop_on_clean_state(repo: Path, worktrees_home: Path) -> None:
    report = reconcile_worktrees()
    assert report.is_clean()


def test_reconcile_removes_orphan_directory(
    repo: Path, worktrees_home: Path,
) -> None:
    root = worktrees_root()
    orphan = root / "proj-orphan" / "main-ORPHAN01"
    orphan.mkdir(parents=True)
    (orphan / "stuff").write_text("x")

    report = reconcile_worktrees()
    assert any("main-ORPHAN01" in entry for entry in report.orphan_dirs_removed)
    assert not orphan.exists()


def test_reconcile_dry_run_does_not_mutate(
    repo: Path, worktrees_home: Path,
) -> None:
    root = worktrees_root()
    orphan = root / "proj-orphan" / "main-ORPHAN02"
    orphan.mkdir(parents=True)

    report = reconcile_worktrees(dry_run=True)
    assert any("main-ORPHAN02" in entry for entry in report.orphan_dirs_removed)
    assert orphan.exists()


def test_reconcile_clears_stale_worktree_path(
    repo: Path, worktrees_home: Path,
) -> None:
    make_project("proj-stale", "P", str(repo))
    ws = _session_workspace("proj-stale", "s-stale")
    shutil.rmtree(ws)

    report = reconcile_worktrees()
    assert "s-stale" in report.stale_rows_cleared

    row = session_rows.fetch_one("s-stale")
    assert row.worktree_status is None
    assert row.worktree_path == str(ws)
    assert row.worktree_branch == "main-s-stale"


def test_reconcile_preserves_live_session(
    repo: Path, worktrees_home: Path,
) -> None:
    make_project("proj-live", "P", str(repo))
    ws = _session_workspace("proj-live", "s-live")

    report = reconcile_worktrees()
    assert ws.exists()
    assert not report.orphan_dirs_removed
    assert not report.stale_rows_cleared


def test_reconcile_removes_orphan_internals(repo: Path, worktrees_home: Path, tmp_path: Path) -> None:
    import hypergolic.config.settings as config

    orphan = config.session_internals_dir("GONE123") / "harness"
    orphan.mkdir(parents=True)

    report = reconcile_worktrees(dry_run=True)
    assert report.orphan_internals_removed
    assert orphan.exists()

    report = reconcile_worktrees()
    assert not orphan.exists()
