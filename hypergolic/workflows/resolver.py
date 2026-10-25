import logging

from hypergolic.harness.app.lookup import (
    all_workflows,
    find_workflow,
    scoped_workflows,
    unique_workflows,
)
from hypergolic.harness.app.state import get_app
from hypergolic.harness.primitives.bundles import Workflow
from hypergolic.schemas import Session

logger = logging.getLogger(__name__)


def resolve_workflows() -> list[Workflow]:
    return unique_workflows(all_workflows(get_app()))


def resolve_workflows_for_session(session: Session) -> list[Workflow]:
    app = get_app()
    return unique_workflows(scoped_workflows(
        app, app.find_project(session.project_id), app.get_role(session.role),
    ))


def get_workflow(workflow_id: str) -> Workflow | None:
    return find_workflow(resolve_workflows(), workflow_id)


def get_session_workflow(session_id: str) -> tuple[str, str] | None:
    from hypergolic.workflows import workflow_rows

    return workflow_rows.active(session_id)
