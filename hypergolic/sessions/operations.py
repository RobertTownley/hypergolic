import logging
import shutil
from pathlib import Path
from typing import cast


from hypergolic.messages import message_rows
from hypergolic.sessions import session_rows
from hypergolic.db.models import DBMessage, DBSession
from hypergolic.enums import ModelTier
from hypergolic.ids import new_id
from hypergolic.git.sandbox_repo import delete_hypergolic_ref
from hypergolic.git.worktree import worktree_branch_name, worktree_path_for
from hypergolic.git.worktree_lifecycle import schedule_create_and_seed
from hypergolic.sandbox.manager.reap import schedule_reap
from hypergolic.sessions.pins import resolve_repo_shas, validate_pins
from hypergolic.schemas import Session, WorktreeStatus
from hypergolic.git.harness_repo import remove_session_workspaces
from hypergolic.harness.app.state import get_app
from hypergolic.mcptools.sessions import clear_enabled_servers
from hypergolic.telemetry.session_trace import session_start_span

logger = logging.getLogger(__name__)


def _db_to_session(db_session: DBSession, project_path: str) -> Session:
    worktree_status = cast(
        WorktreeStatus | None, db_session.worktree_status
    ) if db_session.worktree_status else None
    return Session(
        id=db_session.id,
        model_tier=db_session.model_tier,
        project_id=db_session.project_id,
        project_path=project_path,
        role=db_session.role,
        parent_id=db_session.parent_id,
        dispatch_prompt=db_session.dispatch_prompt,
        conducted_by=db_session.conducted_by,
        origin=db_session.origin,
        worktree_path=db_session.worktree_path,
        worktree_branch=db_session.worktree_branch,
        base_branch=db_session.base_branch,
        worktree_status=worktree_status,
        repo_pins=db_session.repo_pins or {},
    )


def load_worktree_state(session_id: str) -> tuple[WorktreeStatus | None, str | None]:
    row = session_rows.fetch_one(session_id)
    return cast(WorktreeStatus | None, row.worktree_status), row.worktree_path


def load_conducted_by(session_id: str) -> str | None:
    row = session_rows.fetch(session_id)
    return row.conducted_by if row else None


def load_session(session_id: str) -> Session:
    db_session = session_rows.fetch_one(session_id)
    project = get_app().find_project(db_session.project_id)
    if project is None:
        logger.warning(
            "Session %s references unregistered project %r; the project was "
            "likely removed or renamed in main.py. Loading with an empty "
            "project path; project-scoped tools/skills/workflows are unavailable.",
            session_id,
            db_session.project_id,
        )
    return _db_to_session(db_session, project.path if project else "")


def delete_session_tree(session_id: str) -> None:
    project_paths: dict[str, str] = {p.id: p.path for p in get_app().projects}
    for desc in _session_tree(session_id):
        project_path = project_paths.get(desc.project_id)
        try:
            if desc.worktree_path:
                shutil.rmtree(desc.worktree_path, ignore_errors=True)
            if project_path and desc.worktree_branch:
                delete_hypergolic_ref(project_path, desc.project_id, desc.worktree_branch)
        except Exception:  # pragma: no cover - defensive
            logger.warning("Failed to tear down worktree for session %s", desc.id, exc_info=True)
        remove_session_workspaces(desc.id)
        clear_enabled_servers(desc.id)
    session_rows.delete(session_id)


def _session_tree(root_id: str) -> list[DBSession]:
    tree = [row for row in [session_rows.fetch(root_id)] if row is not None]
    for row in tree:
        tree.extend(session_rows.find(parent_id=row.id))
    return tree


def seed_callback_for(project_obj, session_id: str):
    seed_workspace = project_obj.seed_workspace
    if seed_workspace is None:
        return None

    def seed_callback():
        return seed_workspace(load_session(session_id))

    return seed_callback


def create_session(
    project_id: str,
    base_branch: str,
    model_tier: ModelTier | None = None,
    role: str = "generalist",
    parent_id: str | None = None,
    dispatch_prompt: str | None = None,
    worktree_project_path: Path | None = None,
    origin: str | None = None,
    repo_pins: dict[str, str] | None = None,
    conducted_by: str | None = None,
    app_overrides: dict[str, object] | None = None,
) -> Session:
    if model_tier is None:
        model_tier = get_app().default_model_tier
    session_id = new_id()
    with session_start_span(
        session_id, **{"project.id": project_id, "session.role": role}
    ):
        return _create_session(
            session_id, project_id, base_branch, model_tier, role, parent_id,
            dispatch_prompt, worktree_project_path, origin, repo_pins, conducted_by,
            app_overrides,
        )


def _create_session(
    session_id: str,
    project_id: str,
    base_branch: str,
    model_tier: ModelTier,
    role: str,
    parent_id: str | None,
    dispatch_prompt: str | None,
    worktree_project_path: Path | None,
    origin: str | None,
    repo_pins: dict[str, str] | None,
    conducted_by: str | None = None,
    app_overrides: dict[str, object] | None = None,
) -> Session:
    project_obj = get_app().find_project(project_id)
    if project_obj is None:
        raise ValueError(
            f"Cannot create a session for unregistered project {project_id!r}; "
            "projects are declared in main.py"
        )
    repo_for_worktree = worktree_project_path or Path(project_obj.path)
    pins = validate_pins(repo_pins)
    repo_shas = resolve_repo_shas(
        project_id, project_obj.path, base_branch, pins
    )

    projected_branch = worktree_branch_name(session_id, base_branch)
    projected_path = str(worktree_path_for(project_id, projected_branch))

    seed_callback = seed_callback_for(project_obj, session_id)

    worktree_status: WorktreeStatus = "pending"

    session_rows.insert(DBSession(
        id=session_id,
        model_tier=model_tier,
        role=role,
        project_id=project_id,
        parent_id=parent_id,
        dispatch_prompt=dispatch_prompt,
        conducted_by=conducted_by,
        origin=origin,
        worktree_path=projected_path,
        worktree_branch=projected_branch,
        base_branch=base_branch,
        worktree_status=worktree_status,
        repo_pins=pins or None,
        repo_shas=repo_shas,
        app_overrides=app_overrides or None,
    ))

    session_obj = Session(
        id=session_id,
        model_tier=model_tier,
        project_id=project_id,
        project_path=project_obj.path,
        role=role,
        parent_id=parent_id,
        dispatch_prompt=dispatch_prompt,
        conducted_by=conducted_by,
        origin=origin,
        worktree_path=projected_path,
        worktree_branch=projected_branch,
        base_branch=base_branch,
        worktree_status=worktree_status,
        repo_pins=pins,
    )

    schedule_reap()

    schedule_create_and_seed(
        session_id=session_id,
        project_id=project_id,
        project_path=repo_for_worktree,
        base_branch=base_branch,
        seed_callback=seed_callback,
    )

    return session_obj


def fork_session(source_session_id: str, *, with_workspace: bool = False) -> Session:
    source = load_session(source_session_id)
    if with_workspace:
        if source.worktree_branch is None:
            raise ValueError(
                f"Session {source_session_id!r}'s branch was already merged or "
                "discarded; cannot fork its workspace"
            )
        base_branch = source.worktree_branch
    else:
        base_branch = source.base_branch
    forked = create_session(
        project_id=source.project_id,
        base_branch=base_branch,
        model_tier=source.model_tier,
        role=source.role,
    )
    try:
        message_rows.insert(*(
            DBMessage(
                session_id=forked.id,
                content=row.content,
                sequence=row.sequence,
                model=row.model,
                role=row.role,
                stop_reason=row.stop_reason,
                stop_sequence=row.stop_sequence,
                usage=row.usage,
                truncated=row.truncated,
            )
            for row in message_rows.for_session(source_session_id)
        ))
    except Exception:
        try:
            delete_session_tree(forked.id)
        except Exception:
            logger.exception("Failed to clean up aborted fork %s", forked.id)
        raise
    return forked


def clear_session_worktree_fields(session_id: str, *, clear_branch: bool = False) -> None:
    values: dict = {"worktree_status": None}
    if clear_branch:
        values["worktree_branch"] = None
    session_rows.update(session_id, **values)


