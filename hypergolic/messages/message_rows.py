from sqlalchemy import select, update

from hypergolic.db.engine import get_db
from hypergolic.db.models import DBMessage, MESSAGE_ORDER, MESSAGE_ORDER_DESC


def for_session(session_id: str) -> list[DBMessage]:
    with get_db() as db:
        return list(db.execute(
            select(DBMessage).where(DBMessage.session_id == session_id).order_by(*MESSAGE_ORDER)
        ).scalars())


def last(session_id: str, role: str | None = None) -> DBMessage | None:
    stmt = select(DBMessage).where(DBMessage.session_id == session_id, DBMessage.truncated.is_(False))
    if role is not None:
        stmt = stmt.where(DBMessage.role == role)
    with get_db() as db:
        return db.execute(stmt.order_by(*MESSAGE_ORDER_DESC).limit(1)).scalar_one_or_none()


def insert(*messages: DBMessage) -> None:
    with get_db() as db:
        for message in messages:
            db.add(message)
            db.flush()


def truncate(session_id: str) -> None:
    with get_db() as db:
        db.execute(
            update(DBMessage)
            .where(DBMessage.session_id == session_id, DBMessage.truncated.is_(False))
            .values(truncated=True)
        )


def splice(session_id: str, retire_ids: list[str], message: DBMessage) -> None:
    with get_db() as db:
        db.execute(update(DBMessage).where(DBMessage.id.in_(retire_ids)).values(truncated=True))
        db.execute(
            update(DBMessage)
            .where(DBMessage.session_id == session_id, DBMessage.sequence >= message.sequence)
            .values(sequence=DBMessage.sequence + 1)
        )
        db.add(message)
