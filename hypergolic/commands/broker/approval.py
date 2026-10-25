import asyncio
import logging

from pydantic import BaseModel

from hypergolic.commands import approval_bus
from hypergolic.commands.broker.auth import InvokeRequest
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.tool import Tool
from hypergolic.sandbox.exec_env import ExecRecord
from hypergolic.schemas import Session
from hypergolic.tools.approval import (
    ApprovalRequest,
    ApprovalResponse,
    session_decision,
)
from hypergolic.tools.approval_outcome import record_approval
from hypergolic.tools.approval_view_resolver import resolve_approval_view

logger = logging.getLogger(__name__)

REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
DENY = "DENY"
DELEGATE = "DELEGATE"

NO_HUMAN = (
    "requires approval, but no human is attached to this session right now \u2014 "
    "so approval can never be granted and the call is refused. Use a command "
    "that runs unattended, or report the blocker."
)



def originating_command(record: ExecRecord) -> str:
    """The whole string the agent asked for, which is what the human must see.

    Given ``analytics query x && rm -rf /tmp/probe`` the sandbox shell parses the
    chain and forks the shim with only ``["query", "x"]``; the destructive clause
    never reaches the broker. Approving from a per-operation card would hide it.
    """
    return record.command



def decide(command: Tool, parsed: BaseModel | None, session: Session) -> ToolApprovalDecision:
    """Resolve the command's own policy, then the session-level downgrades.

    The downgrades are :func:`session_decision`, the same function the tool
    path applies. A policy that raises is treated as ``REQUIRE_APPROVAL`` \u2014
    a fail-safe for a bug, not a routine path.
    """
    ctx = ApprovalContext(input=parsed, session=session)
    try:
        decision = command.approval_policy(ctx)
    except Exception:
        logger.warning(
            "Approval policy for command '%s' raised; defaulting to REQUIRE_APPROVAL",
            command.id, exc_info=True,
        )
        decision = ToolApprovalDecision(decision=REQUIRE_APPROVAL)
    return session_decision(decision, session)


async def record_invocation(
    session_id: str,
    request_id: str,
    command: Tool,
    payload: dict,
    approved: bool,
    denial_reason: str | None,
) -> None:
    """Persist every invocation, approved or not.

    Auto-approved commands are reachable by any process in the sandbox, so the
    audit row is the only evidence they ran at all.
    """

    # A synchronous DB write, off the loop the agent's turn is sharing.
    await asyncio.to_thread(
        record_approval,
        session_id=session_id,
        tool_use_id=request_id,
        tool_name=command.id,
        tool_input=payload,
        response=ApprovalResponse(approved=approved, denial_reason=denial_reason),
    )


async def await_approval(
    session: Session,
    request_id: str,
    command: Tool,
    payload: dict,
    record: ExecRecord,
    body: InvokeRequest,
    delegated: bool = False,
    conducted: bool = False,
) -> ApprovalResponse:
    """Ask the human (or, when *delegated*, the parent), or refuse when there is nobody to ask.

    Unlike the tool path, this can be reached while no turn is running — a
    process in the container is free to call at any time. With no channel there is
    no human, which is the same position a child session is in, so the answer is
    the same: refuse rather than hang.
    """

    channel = approval_bus.channel(session.id)
    if channel is None:
        return ApprovalResponse(approved=False, denial_reason=f"`{command.id}` {NO_HUMAN}")

    view = (
        resolve_approval_view(command.approval_view, payload)
        if command.approval_view is not None
        else None
    )
    request = ApprovalRequest(
        request_id=request_id,
        tool_name=command.id,
        tool_input={
            # The full originating string, so a destructive clause chained after
            # the approved command is visible rather than hidden.
            "command": originating_command(record),
            "invocation": " ".join([command.id, *body.argv]),
            "cwd": body.cwd,
            "container": record.container,
            "arguments": payload,
        },
        session_id=session.id,
        approval_view=view,
        tool_display_name=command.name,
        delegated=delegated,
        conducted=conducted,
    )
    return await channel.callback(request)

