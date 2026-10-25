"""Startup recovery for sessions left in flight by a server restart.

In-flight work (streaming turns, pending tool results, dispatch futures
awaiting a child's conclude) lives in server memory and dies with the
process. Message-sequence repair in ``messages.persistence`` already
synthesizes error tool_results for dangling tool_use blocks on the next
load; this module fixes the session *statuses* so nothing stays stuck:

- Dispatched children (``parent_id`` set) become INTERRUPTED — their
  parent's awaiting future is gone, so the dispatch can never resolve.
- Top-level sessions become IDLE and are flagged ``resume_pending``, so
  the next WebSocket connection picks the turn back up (see
  ``sessions.resume``).
- CONCLUDING sessions become CONCLUDED: the distillation child whose
  done-callback would have flipped them died with the process (its own
  in-flight status is swept to INTERRUPTED here too).
- CLI-origin sessions become IDLE without the resume flag: another
  process (``hypergolic run``) owns their turns, and this server has no
  business re-driving them.
- Sessions whose workspace was still provisioning (``worktree_status``
  short of a terminal) get provisioning scheduled again: the daemon thread
  that drove it died with the process, and ``wait_for_ready`` would
  otherwise spin to its timeout on a status nothing advances.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from hypergolic.db.engine import get_db
from hypergolic.db.models import DBSession
from hypergolic.enums import SessionStatus
from hypergolic.git.worktree_lifecycle import schedule_create_and_seed, set_worktree_status
from hypergolic.harness.app.state import get_app
from hypergolic.sessions.operations import seed_callback_for

logger = logging.getLogger(__name__)

IN_FLIGHT_STATUSES = frozenset(
    {
        SessionStatus.THINKING,
        SessionStatus.STREAMING,
        SessionStatus.RETRYING,
        SessionStatus.TOOL_USE,
        SessionStatus.TRUNCATING,
        SessionStatus.AWAITING_APPROVAL,
    }
)

STRANDED_WORKTREE_STATUSES = frozenset(
    {"pending", "creating", "starting_sandbox", "cloning", "seeding"}
)

SETTLED_STATUSES = frozenset({SessionStatus.CONCLUDED, SessionStatus.INTERRUPTED})


def _clear_workspace(path: str | None) -> None:
    if not path or not Path(path).is_dir():
        return
    for child in Path(path).iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def recover_stranded_worktrees() -> int:
    """Re-drive provisioning for sessions whose worker thread died mid-flight."""
    settled = [s.value for s in SETTLED_STATUSES]
    with get_db() as db:
        rows = db.execute(
            select(
                DBSession.id, DBSession.project_id, DBSession.base_branch,
                DBSession.worktree_path,
            ).where(
                DBSession.worktree_status.in_(STRANDED_WORKTREE_STATUSES),
                DBSession.status.not_in(settled),
            )
        ).all()
    app = get_app()
    for sid, project_id, base_branch, worktree_path in rows:
        project = app.find_project(project_id)
        if project is None or not base_branch:
            set_worktree_status(sid, "create_failed")
            continue
        _clear_workspace(worktree_path)
        schedule_create_and_seed(
            session_id=sid, project_id=project_id, project_path=Path(project.path),
            base_branch=base_branch, seed_callback=seed_callback_for(project, sid),
        )
    if rows:
        logger.warning(
            "Re-provisioning %d workspace(s) stranded by restart: %s",
            len(rows), [sid for sid, *_ in rows],
        )
    return len(rows)


def recover_in_flight_sessions() -> int:
    """Reset sessions stranded in flight by a restart. Returns rows fixed."""
    in_flight = [s.value for s in IN_FLIGHT_STATUSES]
    with get_db() as db:
        rows = db.execute(
            select(DBSession.id, DBSession.parent_id, DBSession.origin).where(
                DBSession.status.in_(in_flight)
            )
        ).all()
        children = [sid for sid, parent_id, _ in rows if parent_id]
        top_level = [sid for sid, parent_id, origin in rows if not parent_id and origin != "cli"]
        cli_owned = [sid for sid, parent_id, origin in rows if not parent_id and origin == "cli"]
        if children:
            db.execute(
                update(DBSession)
                .where(DBSession.id.in_(children))
                .values(status=SessionStatus.INTERRUPTED.value)
            )
        if top_level:
            db.execute(
                update(DBSession)
                .where(DBSession.id.in_(top_level))
                .values(status=SessionStatus.IDLE.value, resume_pending=True)
            )
        if cli_owned:
            db.execute(
                update(DBSession)
                .where(DBSession.id.in_(cli_owned))
                .values(status=SessionStatus.IDLE.value)
            )
        stuck_concluding = cast(CursorResult[Any], db.execute(
            update(DBSession)
            .where(DBSession.status == SessionStatus.CONCLUDING.value)
            .values(
                status=SessionStatus.CONCLUDED.value,
                concluded_at=datetime.now(timezone.utc),
            )
        )).rowcount

    if rows or stuck_concluding:
        logger.warning(
            "Recovered %d in-flight session(s) after restart "
            "(interrupted children: %s; idled top-level, pending resume: %s; "
            "concluding -> concluded: %d)",
            len(rows), children, top_level, stuck_concluding,
        )
    return len(rows) + stuck_concluding
