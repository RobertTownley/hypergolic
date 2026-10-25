import logging
from pathlib import Path
from typing import Any


from hypergolic.schemas import Session
from hypergolic.harness.app.lookup import find_scoped_workflow
from hypergolic.harness.app.state import get_app
from hypergolic.workflows.resolver import get_session_workflow

logger = logging.getLogger(__name__)


def resolve_roles() -> list[dict[str, Any]]:
    app = get_app()
    roles: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for role in app.roles:
        if role.id not in seen_ids:
            prompt_path = ""
            if role.prompt_path:
                prompt_path = str(Path(role.prompt_path).expanduser())
            roles.append({
                "id": role.id,
                "name": role.name,
                "prompt_path": prompt_path,
                "prompt": role.prompt if hasattr(role, "prompt") else None,
                "tools": [t.id for t in role.tools] if role.tools else [],
                "skills": [s.id for s in role.skills] if role.skills else [],
                "source": "harness",
            })
            seen_ids.add(role.id)

    return roles


def resolve_session_skills(session: Session) -> list[dict[str, Any]]:
    """Collect skills available to a specific session.

    Session-aware: only skills from the session's own project, role, and active
    workflow. This is what the UI reports; the commands those skills contribute
    are materialized into ``/tools`` regardless.
    """

    app = get_app()
    skills_data: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add_skill(s: Any) -> None:
        """Add a skill and, recursively, its children.

        Nested skills materialize into ``/tools`` too, so the modal has to count
        them or it disagrees with what the agent can actually read.
        """
        if s.id in seen:
            return
        skills_data.append({
            "id": s.id,
            "name": s.name,
            "description": s.description or "",
            "source": "harness",
        })
        seen.add(s.id)
        for child in s.skills:
            _add_skill(child)

    # 1. App-level skills
    for s in app.skills:
        _add_skill(s)

    # 2. Project skills
    project = app.find_project(session.project_id)
    if project:
        for s in project.skills:
            _add_skill(s)

    # 3. Role skills
    role = app.get_role(session.role)
    if role:
        for s in role.skills:
            _add_skill(s)

    # 4. Workflow and workflow state skills
    wf_state = get_session_workflow(session.id)
    if wf_state:
        workflow_id, current_state_id = wf_state
        wf = find_scoped_workflow(
            app, project, app.get_role(session.role), workflow_id,
        )
        if wf:
            for s in wf.skills:
                _add_skill(s)
            for state in wf.states:
                if state.id == current_state_id:
                    for s in state.skills:
                        _add_skill(s)
                    break

    return skills_data
