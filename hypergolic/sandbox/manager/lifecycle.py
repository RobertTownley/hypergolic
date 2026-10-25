import asyncio
import logging


from hypergolic.git.sandbox_repo import GITDIR_VOLUME
from hypergolic.sandbox.manager import docker
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sessions.status import session_ended
from hypergolic.sandbox.manager.provisioning import (
    _cleanup_resolved_config,
    _resolved_config_path,
)
from hypergolic.sandbox.manager.start import _compose_down, _start_lock
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.commands.materialize import discard as discard_tools
from hypergolic.sandbox.exec_env import discard_session_token

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ["pending", "running", "starting", "stopping", "error"]


async def stop_sandbox(
    session_id: str, tool_id: str, sandbox_id: str | None = None,
    *, remove_volumes: bool = False,
) -> None:
    sandbox = await sandbox_rows.get(session_id, sandbox_id or tool_id)
    if sandbox is None or sandbox.status == "stopped":
        return

    await sandbox_rows.update(sandbox.id, status="stopping")
    try:
        if sandbox.compose_project and sandbox.config_path:
            async with _start_lock(sandbox.compose_project):
                await _compose_down(
                    sandbox.compose_project, sandbox.config_path,
                    remove_volumes=remove_volumes,
                )
    finally:
        await sandbox_rows.update(sandbox.id, status="stopped")
        if sandbox.config_path and sandbox.compose_project:
            _cleanup_resolved_config(
                str(_resolved_config_path(sandbox.config_path, sandbox.compose_project))
            )
        logger.info(
            "Sandbox stopped: session=%s tool=%s project=%s",
            session_id, tool_id, sandbox.compose_project,
        )


_cleanup_tasks: set[asyncio.Task] = set()


def schedule_session_sandbox_cleanup(session_id: str) -> None:
    async def _run() -> None:
        try:
            await cleanup_session_sandboxes(session_id)
        except Exception:
            logger.warning(
                "Failed to clean up sandboxes for session %s",
                session_id, exc_info=True,
            )

    try:
        task = asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        logger.warning(
            "Could not schedule sandbox cleanup for session %s (no event loop)",
            session_id,
        )
        return
    _cleanup_tasks.add(task)
    task.add_done_callback(_cleanup_tasks.discard)


async def cleanup_session_sandboxes(session_id: str) -> None:
    sandboxes = await sandbox_rows.find(session_id=session_id, statuses=ACTIVE_STATUSES)
    for sandbox in sandboxes:
        await stop_sandbox(session_id, sandbox.tool_id, remove_volumes=True)

    await remove_session_gitdir_volumes(session_id)


    discard_session_token(session_id)
    discard_tools(session_id)


async def remove_session_gitdir_volumes(session_id: str) -> None:
    rows = await sandbox_rows.find(session_id=session_id)
    for project in {r.compose_project for r in rows if r.compose_project}:
        await remove_gitdir_volume(project)


async def remove_gitdir_volume(compose_project: str) -> None:
    try:
        await docker._run_docker("volume", "rm", "-f", f"{compose_project}_{GITDIR_VOLUME}", timeout=30)
    except (SandboxError, OSError):
        pass


async def _list_compose_projects(*, label: str | None = None) -> set[str] | None:
    filters = ["--filter", f"label={label}"] if label else []
    try:
        result = await docker._run_docker(
            "ps", "-a", *filters, "--format", '{{.Label "com.docker.compose.project"}}',
            timeout=15,
        )
    except (SandboxError, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


async def reconcile_sandbox_rows() -> None:
    rows = await sandbox_rows.find(statuses=ACTIVE_STATUSES)
    if not rows:
        return
    active_projects = await _list_compose_projects()
    if active_projects is None:
        return
    for row in rows:
        if row.compose_project not in active_projects:
            await sandbox_rows.update(row.id, status="stopped")
            if row.config_path and row.compose_project:
                _cleanup_resolved_config(
                    str(_resolved_config_path(row.config_path, row.compose_project))
                )
            if await session_ended(row.session_id):
                await remove_session_gitdir_volumes(row.session_id)
