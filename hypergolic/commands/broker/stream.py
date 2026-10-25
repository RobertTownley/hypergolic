import json
from typing import AsyncIterator
import logging


from pydantic import BaseModel

from hypergolic.commands import approval_bus
from hypergolic.commands.broker.approval import (
    DENY,
    DELEGATE,
    REQUIRE_APPROVAL,
    await_approval,
    decide,
    record_invocation,
)
from hypergolic.commands.broker.auth import InvokeRequest
from hypergolic.commands.broker.parsing import fill_stdin, parse_argv, unroutable_reason
from hypergolic.commands.parsers import UsageError
from hypergolic.harness.bridge import call_handler, run_tool_call_validation
from hypergolic.harness.primitives.results import CommandResult, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.harness.primitives.validation import ValidationResult
from hypergolic.ids import new_id
from hypergolic.sandbox.exec_env import ExecRecord
from hypergolic.schemas import Session
from hypergolic.telemetry.tracing import tracer
from hypergolic.tools.approval_outcome import format_denial
from hypergolic.tools.eval_conduct import conduct_decision, is_conducted_call

logger = logging.getLogger(__name__)

#: Exit codes the shim's caller can branch on. Distinct from the transport
#: failure the shim itself reports (70), so every terminal state \u2014 approved,
#: denied, bad arguments, handler error, connection lost \u2014 is distinguishable.
EXIT_USAGE = 2
EXIT_DENIED = 77  # EX_NOPERM
EXIT_UNAVAILABLE = 69  # EX_UNAVAILABLE


def _frame(kind: str, **fields: object) -> bytes:
    """One newline-delimited JSON frame.

    Framing keeps stdout and stderr separated and lets them arrive incrementally
    instead of buffering until the command finishes.
    """
    return (json.dumps({"type": kind, **fields}) + "\n").encode()


async def _noop_broadcast(_event: object) -> None:
    return None


def _context(command: Tool, session: Session, cwd: str | None) -> ToolContext:
    channel = approval_bus.channel(session.id)
    return ToolContext(
        session=session,
        broadcast=channel.broadcast if channel else _noop_broadcast,  # type: ignore[arg-type]
        tool_id=command.id,
        invocation_cwd=cwd,
    )


async def run_command(command: Tool, parsed: BaseModel | None, ctx: ToolContext) -> CommandResult:
    try:
        result = await call_handler(command, parsed, ctx)
    except Exception as exc:
        logger.error("Tool '%s' failed", command.id, exc_info=True)
        return CommandResult.fail(f"{command.id}: {type(exc).__name__}: {exc}")
    if isinstance(result, CommandResult):
        return result
    if isinstance(result, ToolResult):
        return CommandResult.from_tool_result(result)
    return CommandResult(stdout=str(result))


async def stream(
    session: Session,
    record: ExecRecord,
    command: Tool,
    body: InvokeRequest,
) -> AsyncIterator[bytes]:
    """Parse, approve, execute \u2014 all inside the response body.

    A denial is an ordinary nonzero exit frame preceded by a stderr frame
    explaining it, never an HTTP error, so the shim has exactly one success path
    to implement.

    The span parents on the exec that spawned the shim, so a host command shows
    up inside the turn's trace rather than as a detached HTTP request. The whole
    generator runs in one task (``with_heartbeat``'s pump), so the span stays
    current across yields.
    """
    with tracer.start_as_current_span(
        f"broker {command.id}",
        context=record.trace_context,
        attributes={"session.id": session.id, "broker.command": command.id},
    ) as span:
        async for chunk in _stream(session, record, command, body):
            frame = json.loads(chunk)
            if frame["type"] == "exit":
                span.set_attribute("broker.exit_code", frame["code"])
            yield chunk


async def _stream(
    session: Session,
    record: ExecRecord,
    command: Tool,
    body: InvokeRequest,
) -> AsyncIterator[bytes]:
    request_id = new_id()

    unroutable = unroutable_reason(command)
    if unroutable is not None:
        yield _frame("stderr", data=unroutable + "\n")
        yield _frame("exit", code=EXIT_UNAVAILABLE)
        return

    try:
        parsed = parse_argv(command, fill_stdin(body.argv, body.stdin))
    except UsageError as exc:
        usage = f"\nUsage: {command.usage}" if command.usage else ""
        yield _frame("stderr", data=f"{command.id}: {exc}{usage}\n")
        yield _frame("exit", code=EXIT_USAGE)
        return

    ctx = _context(command, session, body.cwd)
    conducted = await is_conducted_call(command, parsed, session)
    validation = (
        ValidationResult.valid() if conducted
        else await run_tool_call_validation(command, parsed, ctx)
    )
    payload = parsed.model_dump(mode="json") if parsed is not None else {}
    if not validation.is_valid:
        problem = validation.message or ""
        await record_invocation(session.id, request_id, command, payload, False, problem)
        yield _frame("stderr", data=problem + "\n")
        yield _frame("exit", code=1)
        return

    decision = conduct_decision(decide(command, parsed, session), conducted)

    if decision.decision == DENY:
        reason = decision.reason or f"`{command.id}` is not permitted in this session."
        await record_invocation(session.id, request_id, command, payload, False, reason)
        yield _frame("stderr", data=reason + "\n")
        yield _frame("exit", code=EXIT_DENIED)
        return

    if decision.decision in (REQUIRE_APPROVAL, DELEGATE):
        # Human wait time, split out so it does not read as a slow command.
        with tracer.start_as_current_span("broker.approval"):
            response = await await_approval(
                session, request_id, command, payload, record, body,
                delegated=decision.decision == DELEGATE,
                conducted=conducted,
            )
        if response.mock_result is not None:
            await record_invocation(session.id, request_id, command, payload, False, "mocked by parent session")
            stream = "stderr" if response.mock_is_error else "stdout"
            yield _frame(stream, data=response.mock_result.rstrip("\n") + "\n")
            yield _frame("exit", code=1 if response.mock_is_error else 0)
            return
        if not response.approved:
            reason = format_denial(response)
            await record_invocation(session.id, request_id, command, payload, False, reason)
            yield _frame("stderr", data=(reason or "denied") + "\n")
            yield _frame("exit", code=EXIT_DENIED)
            return

    await record_invocation(session.id, request_id, command, payload, True, None)
    result = await run_command(command, parsed, ctx)
    if result.stdout:
        yield _frame("stdout", data=result.stdout)
    if result.stderr:
        yield _frame("stderr", data=result.stderr)
    if validation.message:
        yield _frame("stderr", data=validation.message + "\n")
    yield _frame("exit", code=result.exit_code)
