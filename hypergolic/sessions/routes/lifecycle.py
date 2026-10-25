from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import NoResultFound

from hypergolic.messages import message_rows
from hypergolic.sessions import session_rows
from hypergolic.harness.app.state import get_app
from hypergolic.projects.operations import project_name
from hypergolic.sessions.operations import create_session, delete_session_tree, fork_session
from hypergolic.sessions.routes.listing import workflow_display
from hypergolic.sessions.schemas import (
    CreateSessionRequest,
    ForkSessionRequest,
    RoleInfo,
    SessionResponse,
    SessionSearchRequest,
    SessionSearchResponse,
)
from hypergolic.sessions.search import search_sessions
from hypergolic.sessions.transformers import session_response
from hypergolic.skills.resolver import resolve_roles
from hypergolic.workflows.resolver import get_session_workflow

router = APIRouter()


@router.post("", response_model=SessionResponse)
def create_session_endpoint(req: CreateSessionRequest):
    if get_app().find_project(req.project_id) is None:
        raise HTTPException(status_code=404, detail=f"Project {req.project_id!r} not found")
    session = create_session(
        project_id=req.project_id,
        base_branch=req.base_branch,
        model_tier=req.model_tier,
        role=req.role,
    )
    session_row = session_rows.fetch_one(session.id)
    wf_state = get_session_workflow(session_row.id)
    wf_id = wf_state[0] if wf_state else None
    wf_state_id = wf_state[1] if wf_state else None
    wf_name, wf_state_name = workflow_display(wf_id, wf_state_id, {})
    return session_response(
        session_row, project_name(session_row.project_id),
        workflow_id=wf_id,
        workflow_state_id=wf_state_id,
        workflow_name=wf_name,
        workflow_state_name=wf_state_name,
    )


@router.post("/{session_id}/fork", response_model=SessionResponse)
def fork_session_endpoint(session_id: str, req: ForkSessionRequest | None = None):
    try:
        forked = fork_session(session_id, with_workspace=bool(req and req.with_workspace))
    except NoResultFound:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row = session_rows.fetch_one(forked.id)
    return session_response(row, project_name(row.project_id), len(message_rows.for_session(forked.id)))


@router.get("/roles", response_model=list[RoleInfo])
def list_roles(project_id: str | None = None):
    return [RoleInfo(id=r["id"], name=r["name"], source=r["source"]) for r in resolve_roles()]


@router.post("/search", response_model=SessionSearchResponse)
def search_sessions_endpoint(req: SessionSearchRequest):
    return SessionSearchResponse(matches=search_sessions(req.query, req.project_id, req.max_results))


@router.delete("/{session_id}")
def delete_session_endpoint(session_id: str):
    delete_session_tree(session_id)
    return {"status": "deleted"}
