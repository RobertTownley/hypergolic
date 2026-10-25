import logging
import base64
import os
import shlex
from pathlib import Path

from hypergolic.harness.primitives.results import ToolResult
from hypergolic.sandbox.tool.images import extract_image_blocks
from hypergolic.sandbox.tool.overflow import spill_long_output
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.messages.types import BroadcastEvent
from hypergolic.tools.subprocess_util import format_exec_output
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sandbox.manager.docker import OnChunk
from hypergolic.sandbox.manager.exec import exec_in_sandbox
from hypergolic.sandbox.manager.start import needs_start, start_sandbox
from hypergolic.sandbox.manager.types import ExecResult, SandboxError, SandboxTimeout, SandboxUnavailableError
from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120


def default_timeout() -> int:
    raw = os.environ.get("HYPERGOLIC_DEFAULT_COMMAND_TIMEOUT")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid HYPERGOLIC_DEFAULT_COMMAND_TIMEOUT=%r; falling back to %ds",
            raw,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS


def _format_result(result: ExecResult, stdout: str, images: list[dict]) -> ToolResult:
    text = format_exec_output(stdout, result.stderr, result.returncode)
    return ToolResult(
        content=[{"type": "text", "text": text}, *images],
        is_error=result.returncode != 0,
    )


def _chunk_emitter(ctx: ToolContext) -> OnChunk | None:
    tool_use_id = ctx.tool_use_id
    if tool_use_id is None:
        return None

    async def emit(stream: str, text: str) -> None:
        try:
            await ctx.broadcast(BroadcastEvent(
                type="tool_output_chunk",
                role="system",
                content=[{"tool_use_id": tool_use_id, "stream": stream, "text": text}],
                session_id=ctx.session.id,
            ))
        except Exception:  # noqa: BLE001
            logger.debug("tool_output_chunk broadcast failed", exc_info=True)

    return emit


async def run_in_sandbox(
    ctx: ToolContext,
    config_path: str,
    command: str,
    *,
    sandbox_qualifier: str | None = None,
    container: str | None = None,
    workdir: str | None = None,
    sandbox_id: str | None = None,
    timeout: int | None = None,
) -> ToolResult:
    resolved = str(Path(config_path).expanduser())
    session_id = ctx.session.id
    sid = sandbox_id or ctx.sandbox_id(sandbox_qualifier)
    project_root = str(ctx.session.working_directory())

    sandbox = await sandbox_rows.get(session_id, sid)
    if needs_start(sandbox, resolved):
        try:
            await start_sandbox(
                session_id=session_id,
                tool_id=ctx.tool_id,
                config_path=resolved,
                project_root=project_root,
                sandbox_id=sid,
            )
        except SandboxUnavailableError as e:
            return ToolResult.text(str(e), is_error=True)
        except SandboxError as e:
            return ToolResult.text(f"Sandbox startup failed: {e}", is_error=True)
        try:
            await ctx.broadcast(BroadcastEvent(
                type="sandbox_status_change",
                role="system",
                content=[{"status": "running"}],
                session_id=session_id,
            ))
        except Exception:  # noqa: BLE001
            logger.debug("sandbox_status_change broadcast failed", exc_info=True)

    try:
        result = await exec_in_sandbox(
            session_id=session_id,
            tool_id=ctx.tool_id,
            command=command,
            timeout=timeout if timeout is not None else default_timeout(),
            sandbox_id=sid,
            project_root=project_root,
            container=container,
            workdir=workdir,
            persist_state=True,
            on_chunk=_chunk_emitter(ctx),
        )
    except SandboxTimeout as e:
        return _format_timeout(e, timeout if timeout is not None else default_timeout())
    except SandboxError as e:
        return ToolResult.text(f"Sandbox error: {e}", is_error=True)

    async def _run(cmd: str) -> ExecResult:
        return await exec_in_sandbox(
            session_id=session_id, tool_id=ctx.tool_id, command=cmd, timeout=60,
            sandbox_id=sid, project_root=project_root, container=container,
        )

    async def _fetch_file(path: str) -> bytes:
        r = await _run(f"base64 {shlex.quote(path)}")
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"could not read {path}")
        return base64.b64decode(r.stdout.encode("ascii"), validate=False)

    stdout, images = await extract_image_blocks(result.stdout, _fetch_file)
    formatted = await spill_long_output(
        _format_result(result, stdout, images), _run, ctx.tool_use_id or "last",
    )
    return _prepend_repo_warnings(session_id, sid, formatted)


def _prepend_repo_warnings(session_id: str, sid: str, tool_result: ToolResult) -> ToolResult:
    from hypergolic.sandbox.manager.repo_report import pop_report_warnings

    if sid != SANDBOX_TOOL_ID:
        return tool_result
    warnings = pop_report_warnings(session_id)
    if warnings:
        tool_result.content.insert(0, {
            "type": "text",
            "text": (
                "WARNING - repo convergence failed after sandbox start:\n"
                + "\n".join(warnings)
                + "\nRun run_readiness_probes for a full scorecard.\n---"
            ),
        })
    return tool_result


def _format_timeout(e: SandboxTimeout, timeout: int) -> ToolResult:
    note = f"Command timed out after {timeout}s and was killed."
    parts = [e.stdout] if e.stdout else []
    if e.stderr:
        parts.append(f"[stderr]\n{e.stderr}")
    text = (
        "\n\n".join([note + " Output up to that point:"] + parts)
        if parts else note + " It produced no output."
    )
    return ToolResult.text(text, is_error=True)
