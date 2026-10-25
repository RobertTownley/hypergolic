import asyncio
import logging
import time
from collections.abc import Sequence


from hypergolic.sandbox.manager import docker
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sessions.status import session_ended
from hypergolic.sandbox.manager.provisioning import (
    _compose_project_name,
    config_declares_build,
)
from hypergolic.sandbox.manager.converge import BUILD_TIMEOUT_SECONDS
from hypergolic.sandbox.manager.reap import (
    _has_authoritative_db,
    reap_orphans,
    reap_orphaned_session_dirs,
)
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.telemetry.tracing import root_span, tracer
from hypergolic.sandbox.model.sandbox import ProjectSandbox
from hypergolic.sandbox.tool import write_compose

logger = logging.getLogger(__name__)


async def prebuild_project_images(sandboxes: Sequence[ProjectSandbox]) -> None:
    for sandbox in sandboxes:
        path = write_compose(sandbox)
        if not config_declares_build(path):
            continue
        started = time.monotonic()
        try:
            result = await docker._run_compose(
                "build",
                project_name=_compose_project_name("prebuild", sandbox.id),
                config_path=str(path),
                timeout=BUILD_TIMEOUT_SECONDS,
            )
        except (SandboxError, OSError):
            logger.warning("Prebuild of sandbox %s failed", sandbox.id, exc_info=True)
            continue
        elapsed = time.monotonic() - started
        if result.returncode != 0:
            logger.warning(
                "Prebuild of sandbox %s failed after %.1fs: %s",
                sandbox.id, elapsed, result.stderr.strip()[-2000:],
            )
        else:
            logger.info("Prebuilt sandbox %s images in %.1fs", sandbox.id, elapsed)


async def converge_running_workspaces() -> None:
    from hypergolic.sandbox.manager.converge import converge_workspace_repos
    from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID

    rows = await sandbox_rows.find(status="running", tool_id=SANDBOX_TOOL_ID)
    for row in rows:
        if not await session_ended(row.session_id):
            await converge_workspace_repos(row.session_id, SANDBOX_TOOL_ID)


async def run_startup_maintenance(sandboxes: Sequence[ProjectSandbox]) -> None:
    if not _has_authoritative_db():
        return
    try:
        with root_span("startup.maintenance"):
            with tracer.start_as_current_span("sandbox.reap"):
                await reap_orphans()
            with tracer.start_as_current_span("session_dirs.reap"):
                await asyncio.to_thread(reap_orphaned_session_dirs)
            with tracer.start_as_current_span("workspaces.converge"):
                await converge_running_workspaces()
            with tracer.start_as_current_span("images.prebuild"):
                await prebuild_project_images(sandboxes)
    except Exception:
        logger.warning("Sandbox startup maintenance failed", exc_info=True)

