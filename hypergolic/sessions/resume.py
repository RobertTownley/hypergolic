from __future__ import annotations

import logging

from hypergolic.messages import message_rows
from hypergolic.sessions import session_rows
from hypergolic.enums import SessionStatus
from hypergolic.sessions.status import TERMINAL_STATUSES

logger = logging.getLogger(__name__)


def set_session_resume(session_id: str, pending: bool) -> None:
    session_rows.update(session_id, resume_pending=pending)


def _has_work_to_continue(session_id: str) -> bool:
    last = message_rows.last(session_id)
    if last is None:
        return False
    return last.role != "assistant" or any(
        isinstance(block, dict) and block.get("type") == "tool_use" for block in last.content
    )


def claim_resumable_sessions() -> list[str]:
    rows = session_rows.claim_resume_flags()
    resumable = [
        row.id
        for row in rows
        if not row.parent_id
        and SessionStatus(row.status) not in TERMINAL_STATUSES
        and _has_work_to_continue(row.id)
    ]
    if rows:
        logger.info(
            "Claimed %d resume flag(s) after restart; resuming %s",
            len(rows), resumable,
        )
    return resumable
