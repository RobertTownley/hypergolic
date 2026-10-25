from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

import hypergolic.config.settings as config
from hypergolic.sessions import session_rows
from hypergolic.db.models import DBSandbox
from hypergolic.git.sandbox_repo import GITDIR_VOLUME
from hypergolic.db.engine import get_db
from hypergolic.git.worktree import worktrees_root

logger = logging.getLogger(__name__)


@dataclass
class WorktreeReconcileReport:
    orphan_dirs_removed: list[str] = field(default_factory=list)
    stale_rows_cleared: list[str] = field(default_factory=list)
    orphan_volumes_removed: list[str] = field(default_factory=list)
    orphan_internals_removed: list[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not (
            self.orphan_dirs_removed
            or self.stale_rows_cleared
            or self.orphan_volumes_removed
            or self.orphan_internals_removed
        )


def _reconcile_session_internals(report: WorktreeReconcileReport, dry_run: bool, live_ids: set[str]) -> None:
    sessions_root = config.sessions_internals_root()
    if not sessions_root.is_dir():
        return
    for entry in sessions_root.iterdir():
        if not entry.is_dir() or entry.name in live_ids:
            continue
        report.orphan_internals_removed.append(str(entry))
        if not dry_run:
            shutil.rmtree(entry, ignore_errors=True)


def _reconcile_gitdir_volumes(report: WorktreeReconcileReport, dry_run: bool) -> None:
    suffix = f"_{GITDIR_VOLUME}"
    try:
        listing = subprocess.run(
            ["docker", "volume", "ls", "-q", "--filter", f"name={suffix}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if listing.returncode != 0:
        return
    volumes = [v for v in listing.stdout.split() if v.endswith(suffix)]
    if not volumes:
        return
    with get_db() as db:
        known = {
            row for (row,) in db.execute(
                select(DBSandbox.compose_project)
                .where(DBSandbox.compose_project.is_not(None))
            ).all()
        }
    for volume in volumes:
        if volume.removesuffix(suffix) in known:
            continue
        report.orphan_volumes_removed.append(volume)
        if not dry_run:
            subprocess.run(
                ["docker", "volume", "rm", "-f", volume],
                capture_output=True, timeout=30,
            )


def _iter_orphan_dirs(root: Path, live_dirs: set[Path]):
    if not root.exists():
        return
    for project_dir in root.iterdir():
        if not project_dir.is_dir():
            continue
        found_any_level2 = False
        for entry in project_dir.iterdir():
            if not entry.is_dir():
                continue
            found_any_level2 = True
            if entry.resolve() in live_dirs:
                continue
            yield entry
        if not found_any_level2:
            yield project_dir


def reconcile_worktrees(*, dry_run: bool = False) -> WorktreeReconcileReport:
    report = WorktreeReconcileReport()
    root = worktrees_root()

    sessions = session_rows.find()
    active_sessions = {row.id: row for row in sessions if row.worktree_status is not None}
    live_worktree_dirs = {
        Path(s.worktree_path).resolve() for s in active_sessions.values()
    }

    for orphan in _iter_orphan_dirs(root, live_worktree_dirs):
        report.orphan_dirs_removed.append(str(orphan))
        if not dry_run:
            shutil.rmtree(orphan, ignore_errors=True)

    _reconcile_gitdir_volumes(report, dry_run)

    _reconcile_session_internals(report, dry_run, {row.id for row in sessions})

    for sid, s in active_sessions.items():
        if Path(s.worktree_path).exists():
            continue
        report.stale_rows_cleared.append(sid)
        if not dry_run:
            session_rows.update(sid, worktree_status=None)

    return report
