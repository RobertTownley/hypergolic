from __future__ import annotations

import uuid
from typing import Any

from hypergolic.artifacts import artifact_rows
from hypergolic.db.models import DBArtifact, DBMessage, DBSession
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import get_app, set_app
from hypergolic.harness.project import Project
from hypergolic.ids import new_id
from hypergolic.messages import message_rows
from hypergolic.sessions import session_rows


def make_project(pid: str = "proj-1", name: str = "Test", path: str = "/tmp/test"):
    try:
        app = get_app()
    except RuntimeError:
        app = App()
        set_app(app)

    existing = app.find_project(pid)
    if existing is None:
        app.register_project(
            Project(id=pid, name=name, description="d", git_root=path)
        )
        return app.get_project(pid)

    assert (existing.name, existing.path) == (name, path), (
        f"project {pid!r} already registered as "
        f"({existing.name!r}, {existing.path!r}); "
        f"refusing to shadow with ({name!r}, {path!r})"
    )
    return existing


def make_session(
    project_id: str = "proj-1", sid: str | None = None, *, base_branch: str = "main",
    worktree_path: str | None = None, worktree_branch: str | None = None, **fields: Any,
) -> str:
    session_id = sid or str(uuid.uuid4())
    session_rows.insert(DBSession(
        **{"model_tier": "Medium", "worktree_status": "ready", **fields},
        id=session_id, project_id=project_id, base_branch=base_branch,
        worktree_path=worktree_path or f"/tmp/hg-test-wt/{session_id}",
        worktree_branch=worktree_branch or f"{base_branch}-{session_id[:8]}",
    ))
    return session_id


def make_message(session_id: str, role: str = "user", text: str = "hello", **fields: Any) -> str:
    fields.setdefault("content", [{"type": "text", "text": text}])
    message = DBMessage(id=new_id(), session_id=session_id, role=role, **fields)
    message_rows.insert(message)
    return message.id


def make_artifact(session_id: str, **fields: Any) -> str:
    artifact = DBArtifact(**{
        "workflow_id": "wf-1", "state_id": "state-1", "outcome": "success",
        "artifact_id": "art-1", "content": {"result": "ok"}, **fields,
    }, id=new_id(), session_id=session_id)
    artifact_rows.insert(artifact)
    return artifact.id
