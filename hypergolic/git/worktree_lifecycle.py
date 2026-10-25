from __future__ import annotations

import asyncio
import contextvars
import logging
import shutil
import threading
from pathlib import Path
from typing import Callable, cast, TypedDict


from hypergolic.sessions import session_rows
from hypergolic.config.settings import settings
from hypergolic.git.worktree import worktree_branch_name, worktree_path_for
from hypergolic.harness.app.state import app_context, get_app
from hypergolic.sandbox.manager import reap, repo_creation
from hypergolic.schemas import WorktreeStatus
from hypergolic.telemetry.tracing import tracer

logger = logging.getLogger(__name__)

_ready_events: dict[str, tuple[asyncio.Event, asyncio.AbstractEventLoop | None]] = {}
_ready_events_lock = threading.Lock()


def _get_or_create_event(session_id: str) -> asyncio.Event:
    try:
        running_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None
    with _ready_events_lock:
        entry = _ready_events.get(session_id)
        if entry is None:
            event = asyncio.Event()
            _ready_events[session_id] = (event, running_loop)
            return event
        return entry[0]


def _signal_ready(session_id: str) -> None:
    with _ready_events_lock:
        entry = _ready_events.get(session_id)
    if entry is None:
        return
    event, loop = entry
    if loop is not None and loop.is_running():
        try:
            loop.call_soon_threadsafe(event.set)
            return
        except RuntimeError:
            pass
    event.set()


def _discard_event(session_id: str) -> None:
    with _ready_events_lock:
        _ready_events.pop(session_id, None)


def set_worktree_status(session_id: str, status: WorktreeStatus) -> None:
    session_rows.update(session_id, worktree_status=status)


def _set_status_quietly(session_id: str, status: WorktreeStatus) -> None:
    try:
        set_worktree_status(session_id, status)
    except Exception:
        logger.warning(
            "Failed to set worktree_status=%s for session %s", status, session_id, exc_info=True
        )


def _finish(session_id: str, status: WorktreeStatus) -> None:
    _set_status_quietly(session_id, status)
    _signal_ready(session_id)


def _require_sandbox_project(project_id: str):
    if settings.HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE:
        raise RuntimeError(
            "HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE disables sandboxes, and "
            "session workspaces are provisioned inside them."
        )
    project = get_app().find_project(project_id)
    if project is None:
        raise RuntimeError(f"Unknown project {project_id!r}")
    if project.resolved_sandbox is None:
        raise RuntimeError(
            f"Project {project_id!r} declares no sandbox; session workspaces "
            "are provisioned inside one."
        )
    return project


def _run_on_server_loop(coro) -> None:
    loop = reap._server_loop
    if loop is not None and loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop).result()
    else:
        asyncio.run(coro)


def _provision_in_sandbox(
    *, session_id: str, project, project_path: Path, base_branch: str,
) -> None:
    from hypergolic.sessions.operations import load_session

    branch = worktree_branch_name(session_id, base_branch)
    target = worktree_path_for(project.id, branch)
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise RuntimeError(f"Workspace dir already exists and is not empty: {target}")
    session_rows.update(
        session_id, worktree_path=str(target), worktree_branch=branch, base_branch=base_branch,
    )
    _set_status_quietly(session_id, "starting_sandbox")
    app = get_app()

    async def _provision() -> None:
        with app_context(app):
            await repo_creation.provision_session_repos(
                load_session(session_id), project
            )

    _run_on_server_loop(_provision())


def run_create_and_seed(
    *,
    session_id: str,
    project_id: str,
    project_path: Path,
    base_branch: str,
    seed_callback: Callable[[], object] | None = None,
) -> None:
    _set_status_quietly(session_id, "creating")
    try:
        project = _require_sandbox_project(project_id)
        with tracer.start_as_current_span(
            "workspace.provision", attributes={"session.id": session_id}
        ):
            _provision_in_sandbox(
                session_id=session_id, project=project,
                project_path=project_path, base_branch=base_branch,
            )
    except Exception:
        logger.exception("Workspace provisioning failed for session %s", session_id)
        _finish(session_id, "create_failed")
        return

    if seed_callback is not None:
        _set_status_quietly(session_id, "seeding")
        try:
            with tracer.start_as_current_span(
                "workspace.seed", attributes={"session.id": session_id}
            ):
                result = seed_callback()
                if asyncio.iscoroutine(result):
                    asyncio.run(result)
        except Exception:
            logger.exception("Workspace seeding failed for session %s", session_id)
            _finish(session_id, "seed_failed")
            return

    _finish(session_id, "ready")


def _daemon_thread(target, name: str, kwargs: dict) -> threading.Thread:
    ctx = contextvars.copy_context()
    thread = threading.Thread(
        target=lambda: ctx.run(target, **kwargs), name=name, daemon=True,
    )
    thread.start()
    return thread


def schedule_create_and_seed(
    *,
    session_id: str,
    project_id: str,
    project_path: Path,
    base_branch: str,
    seed_callback: Callable[[], object] | None = None,
) -> threading.Thread:
    _get_or_create_event(session_id)
    return _daemon_thread(
        run_create_and_seed,
        f"worktree-create-{session_id}",
        dict(
            session_id=session_id, project_id=project_id, project_path=project_path,
            base_branch=base_branch, seed_callback=seed_callback,
        ),
    )


class WorktreeUnavailableError(Exception):
    ...


WAIT_FOR_READY_TIMEOUT = 600.0

BACKSTOP_POLL = 0.5


async def wait_for_ready(session_id: str, timeout: float = WAIT_FOR_READY_TIMEOUT) -> None:
    status = _read_status(session_id)
    if status == "ready":
        return
    if status in ("create_failed", "seed_failed"):
        raise WorktreeUnavailableError(
            f"Worktree for session {session_id} is in terminal state {status!r}"
        )

    event = _get_or_create_event(session_id)
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        try:
            await asyncio.wait_for(event.wait(), timeout=BACKSTOP_POLL)
        except TimeoutError:
            pass
        status = _read_status(session_id)
        if status == "ready":
            return
        if status in ("create_failed", "seed_failed") or event.is_set():
            raise WorktreeUnavailableError(
                f"Worktree for session {session_id} did not become ready (status={status!r})"
            )
        if asyncio.get_running_loop().time() >= deadline:
            raise WorktreeUnavailableError(
                f"Timed out after {timeout:.0f}s waiting for the worktree of "
                f"session {session_id} (status={status!r})"
            )


def _read_status(session_id: str) -> WorktreeStatus | None:
    row = session_rows.fetch(session_id)
    return cast(WorktreeStatus, row.worktree_status) if row else None


def run_teardown(*, worktree_path: str | None) -> None:
    if worktree_path:
        shutil.rmtree(worktree_path, ignore_errors=True)


class TeardownKwargs(TypedDict):
    session_id: str
    worktree_path: str | None


def schedule_teardown(*, session_id: str, worktree_path: str | None) -> threading.Thread:
    _discard_event(session_id)
    return _daemon_thread(
        run_teardown,
        f"worktree-teardown-{session_id}",
        dict(worktree_path=worktree_path),
    )
