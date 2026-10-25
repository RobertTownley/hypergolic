from __future__ import annotations

import logging
import traceback as tb_module

from anthropic import APIConnectionError, APIStatusError

from hypergolic.db import audit_rows
from hypergolic.messages import message_rows
from hypergolic.db.models import DBError, DBMessage

logger = logging.getLogger(__name__)


def persist_error_message(session_id: str, detail: str) -> None:
    text = detail if detail and detail.strip() else "(no error detail available)"
    message_rows.insert(DBMessage(
        session_id=session_id,
        content=[{"type": "text", "text": text}],
        role="assistant",
        stop_reason="error",
    ))


def persist_error(session_id: str, exc: BaseException) -> None:
    try:
        audit_rows.insert(DBError(
            session_id=session_id,
            error_type=type(exc).__qualname__,
            message=str(exc),
            traceback="".join(tb_module.format_exception(exc)),
        ))
    except Exception:
        logger.warning("Failed to persist error to database", exc_info=True)


def format_error_detail(exc: Exception) -> str:
    if isinstance(exc, APIConnectionError):
        inner = str(exc) or exc.__class__.__name__
        return f"Lost connection to AI provider: {inner}"
    if isinstance(exc, APIStatusError):
        where = "mid-stream" if exc.status_code == 200 else f"HTTP {exc.status_code}"
        return f"AI provider error ({where}): {exc.message}"
    return str(exc) or exc.__class__.__name__
