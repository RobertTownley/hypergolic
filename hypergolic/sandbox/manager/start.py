import asyncio
import logging
from pathlib import Path

from hypergolic.config.settings import settings
from hypergolic.sandbox.manager import docker
from hypergolic.sandbox.manager.converge import _is_sandbox_ready, ensure_up
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sessions.status import session_ended
from hypergolic.sandbox.manager.provisioning import (
    _cleanup_resolved_config,
    _compose_project_name,
    _config_hash,
    _prepare_run_config,
)
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.telemetry.tracing import tracer

logger = logging.getLogger(__name__)

_start_locks: dict[str, asyncio.Lock] = {}

_detached_tasks: set[asyncio.Task] = set()


def _detach(coro) -> asyncio.Task:
    task = asyncio.ensure_future(coro)
    _detached_tasks.add(task)
    task.add_done_callback(_detached_tasks.discard)
    return task


def _start_lock(compose_project: str) -> asyncio.Lock:
    return _start_locks.setdefault(compose_project, asyncio.Lock())


async def _compose_down(
    compose_project: str, config_path: str, *,
    timeout: int = 90, remove_volumes: bool = False,
) -> None:
    try:
        result = await docker._run_compose(
            "down", "--remove-orphans", *(["-v"] if remove_volumes else []),
            "--timeout", "5",
            project_name=compose_project, config_path=config_path, timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("compose down for %s reported: %s", compose_project, result.stderr.strip())
    except Exception:
        logger.warning("Error running compose down for %s", compose_project, exc_info=True)


def needs_start(sandbox, config_path: str) -> bool:
    return (
        sandbox is None
        or sandbox.status != "running"
        or not sandbox.compose_project
        or sandbox.config_hash != _config_hash(str(Path(config_path).expanduser()))
    )


async def start_sandbox(
    session_id: str,
    tool_id: str,
    config_path: str,
    project_root: str,
    sandbox_id: str | None = None,
) -> str:
    if settings.HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE:
        raise SandboxError(
            "HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE is set: sandboxes are "
            "disabled; run commands on the host via cmd"
        )

    sid = sandbox_id or tool_id
    if await session_ended(session_id):
        raise SandboxError(
            "Session has ended (concluded/interrupted); refusing to start "
            "its sandbox."
        )
    await docker.ensure_docker_available()
    canonical_path = str(Path(config_path).expanduser())

    existing = await sandbox_rows.get(session_id, sid)
    if existing and existing.compose_project and not needs_start(existing, canonical_path):
        return existing.compose_project

    compose_project = _compose_project_name(session_id, sid)

    async with _start_lock(compose_project):
        with tracer.start_as_current_span("sandbox.start", attributes={
            "session.id": session_id, "sandbox.compose_project": compose_project,
        }):
            return await _start_locked(
                session_id=session_id, sid=sid, canonical_path=canonical_path,
                compose_project=compose_project, project_root=project_root,
            )


async def _resolve_row_id(session_id: str, sid: str, canonical_path: str, compose_project: str) -> str:
    existing = await sandbox_rows.get(session_id, sid)
    if existing:
        await sandbox_rows.update(existing.id, status="pending")
        await sandbox_rows.update(existing.id, config_path=canonical_path)
        return existing.id
    row = await sandbox_rows.create(
        session_id, sid, status="pending", config_path=canonical_path, compose_project=compose_project,
    )
    return row.id


async def _start_locked(
    *, session_id: str, sid: str, canonical_path: str, compose_project: str, project_root: str
) -> str:
    if await session_ended(session_id):
        raise SandboxError(
            "Session has ended (concluded/interrupted); refusing to start "
            "its sandbox."
        )
    existing = await sandbox_rows.get(session_id, sid)
    if (
        existing
        and existing.compose_project
        and existing.config_hash == _config_hash(canonical_path)
        and await _is_sandbox_ready(compose_project, existing.config_path)
    ):
        if existing.status != "running":
            await sandbox_rows.update(existing.id, status="running")
        return existing.compose_project

    run_path, targets, external_volumes = _prepare_run_config(canonical_path, compose_project)

    row_id = await _resolve_row_id(session_id, sid, canonical_path, compose_project)

    try:
        await ensure_up(
            session_id=session_id, sid=sid, row_id=row_id,
            compose_project=compose_project, canonical_path=canonical_path,
            run_path=run_path, targets=targets, external_volumes=external_volumes,
            project_root=project_root, build=True,
        )
        logger.info("Sandbox started: session=%s sandbox=%s project=%s", session_id, sid, compose_project)
        return compose_project
    except SandboxError:
        await _compose_down(compose_project, run_path)
        await sandbox_rows.update(row_id, status="error")
        _cleanup_resolved_config(run_path)
        raise
    except asyncio.CancelledError:
        _detach(_abandon_start(compose_project, run_path, canonical_path, row_id))
        raise
    except Exception as e:
        await _compose_down(compose_project, run_path)
        await sandbox_rows.update(row_id, status="error")
        _cleanup_resolved_config(run_path)
        raise SandboxError(f"Failed to start sandbox: {e}") from e


async def _abandon_start(compose_project: str, run_path: str, canonical_path: str, row_id: str) -> None:
    try:
        async with _start_lock(compose_project):
            if await _is_sandbox_ready(compose_project, canonical_path):
                return
            await _compose_down(compose_project, run_path)
            await sandbox_rows.update(row_id, status="error")
            _cleanup_resolved_config(run_path)
    except Exception:
        logger.warning("Failed to clean up cancelled sandbox start %s", compose_project, exc_info=True)
