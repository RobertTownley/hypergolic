"""Tool approval dataclasses and helpers."""

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from hypergolic.config.settings import settings
from hypergolic.harness.bridge import evaluate_harness_approval
from hypergolic.harness.primitives.approval import MCPApprovalContext, ToolApprovalDecision
from hypergolic.tools.approval_view_resolver import resolve_approval_view
from hypergolic.tools.approval_view import ResolvedView
from hypergolic.harness.primitives.tool import Tool
from hypergolic.schemas import Session
from hypergolic.harness.app.state import get_app

logger = logging.getLogger(__name__)

_REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
_ALLOW = "ALLOW"
_DENY = "DENY"
_DELEGATE = "DELEGATE"


@dataclass
class ApprovalRequest:
    #: Identifies this approval, not the tool call that caused it. A broker
    #: invocation has no tool_use_id — several may occur inside one — so the
    #: pending-approval map is keyed on this instead.
    request_id: str
    tool_name: str
    tool_input: dict[str, Any]
    session_id: str | None = None
    approval_view: ResolvedView | None = None
    tool_display_name: str | None = None
    #: Set when the decision was ``DELEGATE``: the callback asks the parent first.
    delegated: bool = False
    conducted: bool = False


@dataclass
class AnnotationItem:
    highlighted_text: str
    comment: str


@dataclass
class ApprovalResponse:
    approved: bool
    denial_reason: str | None = None
    annotations: list[AnnotationItem] | None = None
    #: Set by a parent session (``dispatch --resume --outcome mock``): the call
    #: does not run, and the child gets this text as its result instead.
    mock_result: str | None = None
    mock_is_error: bool = False


ApprovalCallback = Callable[[ApprovalRequest], Awaitable[ApprovalResponse]]


_CLI_APPROVAL_DENIAL = (
    "This tool requires human approval, but this session is driven headlessly "
    "by `hypergolic run` — approval can never be granted, so the call is "
    "denied automatically. Find another way: `/tools/index.md` lists every "
    "command you can reach and each README states its approval posture. If the "
    "task genuinely cannot be done without an approval-gated action, say so in "
    "your reply."
)

_CHILD_APPROVAL_DENIAL = (
    "This tool requires human approval, but you are a child session with no "
    "human in the loop \u2014 approval can never be granted, so the call is "
    "denied automatically. Find another way: `/tools/index.md` lists every "
    "command you can reach and each README states its approval posture, or, if the task "
    "genuinely cannot be done without an approval-gated action, conclude and "
    "report the blocker to your parent session."
)


def resolve_approval_decision(
    tool: Tool,
    tool_input: dict[str, Any],
    session: Session,
) -> ToolApprovalDecision:
    """The tool's own policy, then the session-level downgrades."""
    return session_decision(evaluate_harness_approval(tool, tool_input, session), session)


def session_decision(decision: ToolApprovalDecision, session: Session) -> ToolApprovalDecision:
    """Turn a ``REQUIRE_APPROVAL`` into what this session can actually get.

    Every approval route (tool call, broker command, merge gate) applies this
    one function:

    - ``HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE`` downgrades it to ``ALLOW``.
    - ``DELEGATE`` when a parent answers for the session (see
      :mod:`hypergolic.tools.approval_delegate`): the approval callback asks
      the parent, which may approve only a merge into the child's own base
      branch and must deny or escalate everything else.
    - ``DENY`` for a child nobody waits on, and for headless CLI sessions.

    Explicit ``DENY`` and ``ALLOW`` decisions stand.
    """
    from hypergolic.tools.approval_delegate import can_delegate

    if decision.decision != _REQUIRE_APPROVAL:
        return decision
    if settings.HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE:
        return ToolApprovalDecision(decision=_ALLOW)
    if can_delegate(session.id):
        return ToolApprovalDecision(decision=_DELEGATE)
    if session.parent_id:
        return ToolApprovalDecision(decision=_DENY, reason=_CHILD_APPROVAL_DENIAL)
    if session.origin == "cli":
        return ToolApprovalDecision(decision=_DENY, reason=_CLI_APPROVAL_DENIAL)
    return decision


def resolve_mcp_policy(
    server: str,
    tool_name: str,
    tool_input: dict[str, Any],
    session: Session,
) -> ToolApprovalDecision:
    """The harness' own `mcp_approval_policy`, whatever route reached the call.

    Keyed on server and tool name rather than a synthesized tool id so the `mcp`
    command decides the same way the tool bridge does, from the same allowlists.
    """

    try:
        policy = get_app().mcp_approval_policy
    except RuntimeError:
        policy = None

    if policy is None:
        return ToolApprovalDecision(decision=_REQUIRE_APPROVAL)

    ctx = MCPApprovalContext(server=server, tool=tool_name, input=tool_input, session=session)
    try:
        return policy(ctx)
    except Exception:
        logger.warning(
            "mcp_approval_policy raised an exception for '%s %s'; defaulting to REQUIRE_APPROVAL",
            server,
            tool_name,
            exc_info=True,
        )
        return ToolApprovalDecision(decision=_REQUIRE_APPROVAL)


def build_resolved_view(
    tool: Tool, tool_input: dict[str, Any],
) -> ResolvedView | None:
    """Resolve ``tool.approval_view`` against ``tool_input``; ``None`` if unset."""
    if tool.approval_view is None:
        return None
    return resolve_approval_view(tool.approval_view, tool_input)
