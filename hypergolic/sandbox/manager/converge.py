import asyncio
import logging

from hypergolic.harness.app.state import get_app
from hypergolic.sandbox.manager import docker
from hypergolic.sandbox.manager.compose_env import compose_env
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sandbox.manager.provisioning import (
    _cleanup_resolved_config,
    _config_hash,
    _read_published_ports,
    config_declares_build,
)
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID

logger = logging.getLogger(__name__)

BUILD_TIMEOUT_SECONDS = 1800


async def _is_sandbox_ready(compose_project: str, config_path: str) -> bool:
    try:
        result = await docker._run_compose(
            "ps", "--status", "running", "-q",
            project_name=compose_project, config_path=config_path, timeout=15,
        )
    except SandboxError:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


async def _build_images(compose_project: str, run_path: str, env: dict[str, str]) -> None:
    result = await docker._run_compose(
        "build", project_name=compose_project, config_path=run_path,
        timeout=BUILD_TIMEOUT_SECONDS, env=env,
    )
    if result.returncode != 0:
        raise SandboxError(f"Failed to build sandbox images: {result.stderr.strip()}")


async def ensure_up(
    *,
    session_id: str,
    sid: str,
    row_id: str,
    compose_project: str,
    canonical_path: str,
    run_path: str,
    targets: dict[str, tuple[str, int]],
    external_volumes: list[str],
    project_root: str,
    build: bool,
) -> None:
    for volume_name in external_volumes:
        await docker.ensure_volume(volume_name)

    env = await compose_env(session_id, project_root)
    if build and config_declares_build(run_path):
        await _build_images(compose_project, run_path, env)

    result = await docker._run_compose(
        "up", "-d", "--remove-orphans",
        project_name=compose_project, config_path=run_path, timeout=120, env=env,
    )
    if result.returncode != 0:
        if await _is_sandbox_ready(compose_project, canonical_path):
            await sandbox_rows.update(row_id, status="running")
            await sandbox_rows.update(row_id, config_hash=_config_hash(canonical_path))
            _cleanup_resolved_config(run_path)
            await converge_workspace_repos(session_id, sid)
            return
        raise SandboxError(f"Failed to start sandbox: {result.stderr.strip()}")

    if targets:
        port_map = await _read_published_ports(compose_project, run_path, targets)
        if port_map:
            await sandbox_rows.update(row_id, port_map=port_map)
        else:
            logger.warning(
                "Sandbox %s declared exposed ports but none were read back", compose_project,
            )
    await sandbox_rows.update(row_id, status="running")
    await sandbox_rows.update(row_id, config_hash=_config_hash(canonical_path))
    await converge_workspace_repos(session_id, sid)


async def converge_workspace_repos(session_id: str, sid: str) -> None:
    if sid != SANDBOX_TOOL_ID:
        return
    from hypergolic.sandbox.manager import repo_provision

    try:
        session = await asyncio.to_thread(repo_provision._load_session, session_id)
        if session.worktree_status != "ready":
            return
        project = get_app().find_project(session.project_id)
        if project is None or project.resolved_sandbox is None:
            return
        await repo_provision.provision_sandbox(session, project)
    except Exception:
        logger.warning(
            "Workspace repo convergence failed for session %s", session_id, exc_info=True,
        )
