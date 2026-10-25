from collections.abc import Collection
from typing import Any

from sqlalchemy import select, update as sa_update

from hypergolic.db.engine import run_db
from hypergolic.db.models import DBSandbox


async def get(session_id: str, tool_id: str) -> DBSandbox | None:
    return await run_db(lambda db: db.execute(
        select(DBSandbox).where(DBSandbox.session_id == session_id, DBSandbox.tool_id == tool_id)
    ).scalar_one_or_none())


async def find(*, statuses: Collection[str] = (), **criteria: Any) -> list[DBSandbox]:
    stmt = select(DBSandbox).filter_by(**criteria)
    if statuses:
        stmt = stmt.where(DBSandbox.status.in_(statuses))
    return await run_db(lambda db: list(db.execute(stmt).scalars()))


async def create(session_id: str, tool_id: str, **fields: Any) -> DBSandbox:
    def _create(db) -> DBSandbox:
        row = DBSandbox(session_id=session_id, tool_id=tool_id, **fields)
        db.add(row)
        db.flush()
        db.refresh(row)
        return row

    return await run_db(_create)


async def update(sandbox_id: str, **values: Any) -> None:
    await run_db(lambda db: db.execute(
        sa_update(DBSandbox).where(DBSandbox.id == sandbox_id).values(**values)
    ))
