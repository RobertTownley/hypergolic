from sqlalchemy import func, select, update

from hypergolic.db.engine import get_db, run_db
from hypergolic.db.models import DBSessionWorkflow


def _live(session_id: str):
    return (DBSessionWorkflow.session_id == session_id, DBSessionWorkflow.deleted_at.is_(None))


def active(session_id: str) -> tuple[str, str] | None:
    with get_db() as db:
        row = db.execute(select(DBSessionWorkflow).where(*_live(session_id))).scalar_one_or_none()
        return None if row is None else (row.workflow_id, row.current_state_id)


async def start(session_id: str, workflow_id: str, state_id: str) -> None:
    await run_db(lambda db: db.add(DBSessionWorkflow(
        session_id=session_id, workflow_id=workflow_id, current_state_id=state_id,
    )))


async def move(session_id: str, state_id: str) -> None:
    await run_db(lambda db: db.execute(
        update(DBSessionWorkflow).where(*_live(session_id)).values(current_state_id=state_id)
    ))


async def end(session_id: str) -> None:
    await run_db(lambda db: db.execute(
        update(DBSessionWorkflow).where(*_live(session_id)).values(deleted_at=func.now())
    ))
