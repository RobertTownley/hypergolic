from typing import Any

from sqlalchemy import select

from hypergolic.db.engine import get_db, run_db
from hypergolic.db.models import DBArtifact


def get(artifact_db_id: str) -> DBArtifact | None:
    with get_db() as db:
        return db.get(DBArtifact, artifact_db_id)


def find(
    *, newest_first: bool = False, offset: int = 0, limit: int | None = None, **criteria: Any,
) -> list[DBArtifact]:
    order = (DBArtifact.created_at.desc(), DBArtifact.id.desc()) if newest_first else (
        DBArtifact.created_at, DBArtifact.id)
    with get_db() as db:
        return list(db.execute(
            select(DBArtifact).filter_by(**criteria).order_by(*order).offset(offset).limit(limit)
        ).scalars())


def insert(row: DBArtifact) -> None:
    with get_db() as db:
        db.add(row)


async def add(row: DBArtifact) -> None:
    await run_db(lambda db: db.add(row))
