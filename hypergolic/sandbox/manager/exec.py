import logging
import time

from hypergolic.db.models import DBSandbox
from hypergolic.sandbox.exec_env import exec_argv, exec_env, register_exec, release_exec
from hypergolic.sandbox.manager import docker
from hypergolic.sandbox.manager.docker import OnChunk
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sessions.status import session_ended
from hypergolic.sandbox.manager.converge import ensure_up
from hypergolic.sandbox.manager.start import _start_lock
from hypergolic.sandbox.manager.provisioning import (
    _cleanup_resolved_config,
    _find_default_service,
    _parse_config,
    _prepare_run_config,
)
from hypergolic.telemetry.exec_metrics import ExecMeter
from hypergolic.telemetry.tracing import tracer
from hypergolic.sandbox.manager.types import (
    ExecResult,
    SandboxError,
    SandboxNotReadyError,
    SandboxUnavailableError,
)

logger = logging.getLogger(__name__)

_CONTAINER_DOWN_PATTERNS = (
    "is not running",
    "no container found",
    "has no container",
    "no such container",
)


def _is_container_down_error(stderr: str) -> bool:
    text = stderr.lower()
    return any(pat in text for pat in _CONTAINER_DOWN_PATTERNS)


async def _recover_container(sandbox: DBSandbox, project_root: str | None) -> bool:
    if not sandbox.compose_project or project_root is None:
        return False
    try:
        await docker.ensure_docker_available()
    except SandboxUnavailableError:
        return False

    async with _start_lock(sandbox.compose_project):
        if await session_ended(sandbox.session_id):
            logger.info(
                "Not recovering sandbox %s: session %s has ended",
                sandbox.compose_project, sandbox.session_id,
            )
            return False
        return await _recover_container_locked(sandbox, project_root, sandbox.compose_project)


async def _recover_container_locked(
    sandbox: DBSandbox, project_root: str, compose_project: str,
) -> bool:

    try:
        run_path, targets, external_volumes = _prepare_run_config(sandbox.config_path, compose_project)
    except SandboxError:
        logger.warning(
            "Cannot recover sandbox %s: config %s is missing",
            compose_project, sandbox.config_path,
        )
        await sandbox_rows.update(sandbox.id, status="error")
        return False

    try:
        await ensure_up(
            session_id=sandbox.session_id, sid=sandbox.tool_id, row_id=sandbox.id,
            compose_project=compose_project, canonical_path=sandbox.config_path,
            run_path=run_path, targets=targets, external_volumes=external_volumes,
            project_root=project_root, build=False,
        )
    except SandboxError as e:
        logger.warning(
            "Sandbox recovery failed: project=%s err=%s", compose_project, e,
        )
        await sandbox_rows.update(sandbox.id, status="error")
        _cleanup_resolved_config(run_path)
        return False

    logger.info("Sandbox recovered: project=%s", compose_project)
    return True


async def exec_in_sandbox(
    session_id: str,
    tool_id: str,
    command: str,
    timeout: int = 30,
    sandbox_id: str | None = None,
    project_root: str | None = None,
    container: str | None = None,
    workdir: str | None = None,
    persist_state: bool = False,
    restore_cwd: bool = True,
    on_chunk: OnChunk | None = None,
) -> ExecResult:
    sandbox = await sandbox_rows.get(session_id, sandbox_id or tool_id)

    if sandbox is None:
        raise SandboxNotReadyError("Sandbox is starting up.")

    if sandbox.status == "error":
        raise SandboxError(
            "Sandbox is in error state. The container failed to start. "
            "Check Docker logs or ask the user to investigate."
        )

    if sandbox.status == "pending":
        raise SandboxNotReadyError("Sandbox is starting up.")

    if sandbox.status != "running":
        raise SandboxError(
            f"Sandbox is in '{sandbox.status}' state, expected 'running'. "
            "This may indicate a startup failure."
        )

    if not sandbox.compose_project:
        raise SandboxError("Sandbox has no compose project name. This is a bug.")

    try:
        config = _parse_config(sandbox.config_path)
    except SandboxError:
        config = None

    if container is not None:
        if config is not None:
            services = config.get("services", {})
            if container not in services:
                raise SandboxError(
                    f"Container '{container}' is not defined in this sandbox. "
                    f"Available: {sorted(services)}"
                )
        service_name = container
    elif config is not None:
        service_name = _find_default_service(config)
    else:
        service_name = "app"

    with tracer.start_as_current_span("sandbox.exec", attributes={
        "session.id": session_id,
        "sandbox.compose_project": sandbox.compose_project,
        "sandbox.container": service_name,
        "exec.timeout_s": timeout,
    }) as span:
        exec_id = register_exec(
            session_id=session_id,
            command=command,
            container=service_name,
            sandbox_id=sandbox_id or tool_id,
        )
        started = time.monotonic()
        first_output = False

        async def traced_chunk(name: str, text: str) -> None:
            nonlocal first_output
            if not first_output:
                first_output = True
                span.set_attribute(
                    "exec.first_output_ms", round((time.monotonic() - started) * 1000)
                )
            if on_chunk is not None:
                await on_chunk(name, text)

        meter = ExecMeter(span, sandbox.compose_project, service_name, command)
        try:
            result = await _run_exec(
                sandbox, project_root, session_id, exec_id, service_name, command,
                timeout=timeout, workdir=workdir, persist_state=persist_state,
                restore_cwd=restore_cwd, on_chunk=traced_chunk,
            )
        except BaseException:
            meter.abandon()
            raise
        await meter.finish()
        span.set_attributes({
            "exec.exit_code": result.returncode,
            "exec.stdout_bytes": len(result.stdout),
            "exec.stderr_bytes": len(result.stderr),
        })
        return result


async def _run_exec(
    sandbox: DBSandbox,
    project_root: str | None,
    session_id: str,
    exec_id: str,
    service_name: str,
    command: str,
    *,
    timeout: int,
    workdir: str | None,
    persist_state: bool,
    restore_cwd: bool,
    on_chunk: OnChunk,
) -> ExecResult:
    assert sandbox.compose_project
    try:
        exec_args = ["exec", "-T", *exec_env(session_id, exec_id)]
        if workdir is not None:
            exec_args += ["-w", workdir]
        exec_args += [service_name, *exec_argv(
            command, persist_state=persist_state, restore_cwd=restore_cwd
        )]

        result = await docker._run_compose(
            *exec_args,
            project_name=sandbox.compose_project,
            config_path=sandbox.config_path,
            timeout=timeout,
            suspend_key=exec_id,
            on_chunk=on_chunk,
        )

        if result.returncode != 0 and _is_container_down_error(result.stderr):
            logger.info(
                "Sandbox container appears down, attempting recovery: "
                "session=%s project=%s",
                session_id, sandbox.compose_project,
            )
            with tracer.start_as_current_span("sandbox.recover"):
                recovered = await _recover_container(sandbox, project_root)
            if recovered:
                result = await docker._run_compose(
                    *exec_args,
                    project_name=sandbox.compose_project,
                    config_path=sandbox.config_path,
                    timeout=timeout,
                    suspend_key=exec_id,
                    on_chunk=on_chunk,
                )

        return result
    finally:
        release_exec(exec_id)
