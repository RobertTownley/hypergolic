from fastapi import APIRouter
from sqlalchemy import select, func

from hypergolic.db.engine import get_db
from hypergolic.db.models import DBSession, DBMessage, DBSessionWorkflow
from hypergolic.harness.primitives.bundles import Workflow
from hypergolic.projects.operations import project_name
from hypergolic.sessions.schemas import SessionResponse
from hypergolic.sessions.transformers import session_response
from hypergolic.workflows.resolver import get_workflow

router = APIRouter()


def workflow_display(
    wf_id: str | None,
    wf_state_id: str | None,
    cache: dict[str, Workflow | None],
) -> tuple[str | None, str | None]:
    """(workflow name, state name) for a session's active workflow, if any."""
    if not wf_id:
        return None, None
    if wf_id not in cache:
        cache[wf_id] = get_workflow(wf_id)
    wf = cache[wf_id]
    if not wf:
        return None, None
    state_name = next((s.name for s in wf.states if s.id == wf_state_id), None)
    return wf.name, state_name


@router.get("", response_model=list[SessionResponse])
def list_sessions(project_id: str | None = None):
    with get_db() as db:
        msg_count_subq = (
            select(DBMessage.session_id, func.count(DBMessage.id).label("msg_count"))
            .group_by(DBMessage.session_id)
            .subquery()
        )
        active_wf_subq = (
            select(
                DBSessionWorkflow.session_id,
                DBSessionWorkflow.workflow_id,
                DBSessionWorkflow.current_state_id,
            )
            .where(DBSessionWorkflow.deleted_at.is_(None))
            .subquery()
        )
        stmt = (
            select(
                DBSession,
                msg_count_subq.c.msg_count,
                active_wf_subq.c.workflow_id,
                active_wf_subq.c.current_state_id,
            )
            .outerjoin(msg_count_subq, DBSession.id == msg_count_subq.c.session_id)
            .outerjoin(active_wf_subq, DBSession.id == active_wf_subq.c.session_id)
            .order_by(
                (func.coalesce(msg_count_subq.c.msg_count, 0) == 0).desc(),
                DBSession.updated_at.desc(),
            )
        )
        if project_id:
            stmt = stmt.where(DBSession.project_id == project_id)
        rows = db.execute(stmt).all()

    wf_configs: dict[str, Workflow | None] = {}
    return [
        session_response(
            session, project_name(session.project_id), msg_count or 0,
            workflow_id=wf_id,
            workflow_state_id=wf_state_id,
            workflow_name=(names := workflow_display(wf_id, wf_state_id, wf_configs))[0],
            workflow_state_name=names[1],
        )
        for session, msg_count, wf_id, wf_state_id in rows
    ]
