from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from hypergolic.db.engine import get_db, run_db
from hypergolic.db.models import DBSkillActivation


async def record(session_id: str, skill_id: str) -> None:
    def _insert(db) -> None:
        db.execute(
            insert(DBSkillActivation)
            .values(session_id=session_id, skill_id=skill_id)
            .on_conflict_do_nothing(constraint="uq_skill_activations_session_skill")
        )

    await run_db(_insert)


def skill_ids(session_id: str) -> list[str]:
    with get_db() as db:
        rows = db.execute(
            select(DBSkillActivation.skill_id)
            .where(DBSkillActivation.session_id == session_id)
            .order_by(DBSkillActivation.created_at, DBSkillActivation.id)
        )
        return [r[0] for r in rows]
