from typing import Any, cast

from sqlalchemy import CursorResult, delete as sa_delete, select, update as sa_update
from sqlalchemy.exc import NoResultFound

from hypergolic.db.engine import get_db, run_db
from hypergolic.db.models import DBSession


def insert(row: DBSession) -> None:
    with get_db() as db:
        db.add(row)


def fetch(session_id: str) -> DBSession | None:
    with get_db() as db:
        return db.get(DBSession, session_id)


def fetch_one(session_id: str) -> DBSession:
    row = fetch(session_id)
    if row is None:
        raise NoResultFound(f"No session {session_id!r}")
    return row


def find(**criteria: Any) -> list[DBSession]:
    with get_db() as db:
        return list(db.execute(
            select(DBSession).filter_by(**criteria).order_by(DBSession.created_at, DBSession.id)
        ).scalars())


async def atransition(session_id: str, from_status: str, **values: Any) -> bool:
    result = await run_db(lambda db: db.execute(
        sa_update(DBSession).where(DBSession.id == session_id, DBSession.status == from_status).values(**values)
    ))
    return bool(cast(CursorResult[Any], result).rowcount)


def claim_resume_flags() -> list[DBSession]:
    with get_db() as db:
        return list(db.execute(
            sa_update(DBSession).where(DBSession.resume_pending.is_(True))
            .values(resume_pending=False).returning(DBSession)
        ).scalars())


def delete(session_id: str) -> None:
    with get_db() as db:
        db.execute(sa_delete(DBSession).where(DBSession.id == session_id))


async def afetch(session_id: str) -> DBSession | None:
    return await run_db(lambda db: db.get(DBSession, session_id))


def update(session_id: str, **values: Any) -> None:
    with get_db() as db:
        db.execute(sa_update(DBSession).where(DBSession.id == session_id).values(**values))


async def aupdate(session_id: str, **values: Any) -> None:
    await run_db(lambda db: db.execute(
        sa_update(DBSession).where(DBSession.id == session_id).values(**values)
    ))
