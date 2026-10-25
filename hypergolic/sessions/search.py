from typing import Any

from sqlalchemy import String as SAString, func, select
from sqlalchemy.sql.expression import cast

from hypergolic.db.engine import get_db
from hypergolic.db.models import DBMessage, DBSession, MESSAGE_ORDER
from hypergolic.projects.operations import project_name
from hypergolic.db.utils import to_iso_utc
from hypergolic.sessions.schemas import SessionSearchMatch

MAX_SNIPPET = 200


def extract_text(content: list[Any]) -> str:
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def _content_contains(query: str):
    return cast(DBMessage.content, SAString).contains(query)


def _build_match_subquery(query: str, project_id: str | None):
    stmt = (
        select(DBMessage.session_id.label("sid"), func.min(DBMessage.id).label("mid"))
        .where(_content_contains(query))
        .group_by(DBMessage.session_id)
    )
    if project_id:
        stmt = stmt.join(DBSession, DBMessage.session_id == DBSession.id).where(
            DBSession.project_id == project_id
        )
    return stmt.subquery()


def _get_first_user_message(db, session_id: str) -> str | None:
    msg = db.execute(
        select(DBMessage)
        .where(DBMessage.session_id == session_id, DBMessage.role == "user")
        .order_by(*MESSAGE_ORDER)
        .limit(1)
    ).scalar_one_or_none()
    if not msg:
        return None
    text = extract_text(msg.content)
    return text[:MAX_SNIPPET] if len(text) > MAX_SNIPPET else text


def search_sessions(
    query: str, project_id: str | None = None, max_results: int = 20,
) -> list[SessionSearchMatch]:
    with get_db() as db:
        match_subq = _build_match_subquery(query, project_id)
        msg_count_subq = (
            select(DBMessage.session_id, func.count(DBMessage.id).label("msg_count"))
            .group_by(DBMessage.session_id)
            .subquery()
        )
        stmt = (
            select(DBSession, DBMessage, msg_count_subq.c.msg_count)
            .join(match_subq, DBSession.id == match_subq.c.sid)
            .join(DBMessage, DBMessage.id == match_subq.c.mid)
            .outerjoin(msg_count_subq, DBSession.id == msg_count_subq.c.session_id)
            .order_by(DBSession.updated_at.desc())
            .limit(max_results)
        )
        rows = db.execute(stmt).all()
        results: list[SessionSearchMatch] = []
        for session, msg, msg_count in rows:
            match_text = extract_text(msg.content)[:MAX_SNIPPET]
            results.append(SessionSearchMatch(
                session_id=session.id,
                project_id=session.project_id,
                project_name=project_name(session.project_id),
                model_tier=session.model_tier,
                created_at=to_iso_utc(session.created_at),
                updated_at=to_iso_utc(session.updated_at),
                message_count=msg_count or 0,
                match_text=match_text,
                match_role=msg.role,
                first_message=_get_first_user_message(db, session.id),
            ))
    return results
