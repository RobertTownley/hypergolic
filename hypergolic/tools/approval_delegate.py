"""DELEGATE: a child's approvals go to the parent that waits on it.

A gated call in a child resolves to ``DELEGATE`` (see
:func:`hypergolic.tools.approval.session_decision`) when its agent parent is
blocked in ``dispatch``: the request ends that call early and the parent
answers with ``dispatch --resume``.

Every route (tool call, broker command, merge gate) reaches the same approval
callback, which hands a delegated request to :func:`ask`. The parent may
*approve* only an ``app`` ``land`` into the child's own base branch — the
parent's live branch, or the branch its dispatch made for an app pin. For every
other request the parent can deny, escalate, or *mock*: answer with a result
of its own, so the call never runs (how a parent conducts a simulated
session). A merge gate cannot be mocked: approve it or deny it.
The rule lives here, not in any prompt, so no agent can widen it.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

from hypergolic.tools.approval import AnnotationItem, ApprovalRequest, ApprovalResponse

AskHuman = Callable[[ApprovalRequest], Awaitable[ApprovalResponse]]
Outcome = Literal["approve", "deny", "escalate", "mock"]

_LAND = "land"
_APP_REPO = "app"
_MAX_INPUT_CHARS = 4_000

NO_PARENT = (
    "This call needs approval, and your parent session is no longer waiting "
    "on you, so nobody can grant it. Commit your work and conclude, and "
    "report the blocker."
)


@dataclass
class PendingApproval:
    request: ApprovalRequest
    child_id: str
    parent_may_approve: bool
    #: ``None`` means "escalate to the human".
    future: asyncio.Future[ApprovalResponse | None] = field(repr=False)


@dataclass(frozen=True)
class _Parent:
    base_branch: str
    inbox: asyncio.Queue[PendingApproval]


_PARENTS: dict[str, _Parent] = {}
_PENDING: dict[str, PendingApproval] = {}


def open_inbox(child_id: str, base_branch: str) -> asyncio.Queue[PendingApproval]:
    """Route *child_id*'s approvals to its waiting agent parent."""
    existing = _PARENTS.get(child_id)
    if existing is not None:
        return existing.inbox
    inbox: asyncio.Queue[PendingApproval] = asyncio.Queue()
    _PARENTS[child_id] = _Parent(base_branch=base_branch, inbox=inbox)
    return inbox


def close(child_id: str) -> None:
    """Stop delegating for *child_id*; deny whatever still waits on its parent."""
    _PARENTS.pop(child_id, None)
    for rid, pending in list(_PENDING.items()):
        if pending.child_id != child_id:
            continue
        _PENDING.pop(rid, None)
        if not pending.future.done():
            pending.future.set_result(ApprovalResponse(approved=False, denial_reason=NO_PARENT))


def inbox_for(child_id: str) -> asyncio.Queue[PendingApproval] | None:
    parent = _PARENTS.get(child_id)
    return parent.inbox if parent is not None else None


def can_delegate(session_id: str) -> bool:
    return session_id in _PARENTS


def parent_may_approve(req: ApprovalRequest, base_branch: str) -> bool:
    if req.tool_name != _LAND:
        return False
    args = req.tool_input.get("arguments")
    if not isinstance(args, dict):
        return False
    return args.get("repo") == _APP_REPO and args.get("branch") == base_branch


async def ask(req: ApprovalRequest, ask_human: AskHuman) -> ApprovalResponse:
    """The parent's answer to a delegated request (or the human's, on escalate)."""
    parent = _PARENTS.get(req.session_id or "")
    if parent is None:
        return ApprovalResponse(approved=False, denial_reason=NO_PARENT)
    may_approve = parent_may_approve(req, parent.base_branch)
    future: asyncio.Future[ApprovalResponse | None] = asyncio.get_running_loop().create_future()
    pending = PendingApproval(
        request=req, child_id=req.session_id or "", parent_may_approve=may_approve, future=future,
    )
    _PENDING[req.request_id] = pending
    await parent.inbox.put(pending)
    try:
        response = await future
    finally:
        _PENDING.pop(req.request_id, None)
    return response if response is not None else await ask_human(req)


def child_of(request_id: str) -> str | None:
    pending = _PENDING.get(request_id)
    return pending.child_id if pending is not None else None


def answer(
    request_id: str, parent_id: str, outcome: Outcome, message: str = "",
    result: str | None = None, result_is_error: bool = False,
) -> str | None:
    """Resolve a pending request for *parent_id*; an error string when refused."""
    from hypergolic.dispatch.state import _child_to_parent

    pending = _PENDING.get(request_id)
    if pending is None or pending.future.done():
        return f"no approval request {request_id!r} is waiting"
    if _child_to_parent.get(pending.child_id) != parent_id:
        return f"approval request {request_id!r} is not from one of your children"
    if outcome == "approve" and not pending.parent_may_approve:
        return (
            f"only the user can approve `{pending.request.tool_name}` for a child. "
            "Deny it (with a reason), or escalate it to the user."
        )
    if outcome == "mock":
        if pending.request.tool_name == _LAND:
            return "a merge gate cannot be mocked: approve it or deny it"
        if result is None:
            return "mock needs --result: the text the child gets as the tool result"
        pending.future.set_result(ApprovalResponse(
            approved=False, mock_result=result, mock_is_error=result_is_error,
        ))
    elif outcome == "escalate":
        pending.future.set_result(None)
    elif outcome == "approve":
        # No highlight: the note reads like a user's general approval comment.
        notes = [AnnotationItem(highlighted_text="", comment=message)] if message else None
        pending.future.set_result(ApprovalResponse(approved=True, annotations=notes))
    else:
        pending.future.set_result(ApprovalResponse(approved=False, denial_reason=message or None))
    return None


def describe(pending: PendingApproval) -> str:
    """What the parent reads when its ``dispatch`` call returns for a request."""
    req = pending.request
    shown = json.dumps(req.tool_input, indent=2, default=str)
    if len(shown) > _MAX_INPUT_CHARS:
        shown = shown[:_MAX_INPUT_CHARS] + "\n... [truncated]"
    if pending.parent_may_approve:
        choices = "approve|deny|escalate"
    elif req.tool_name == _LAND:
        choices = "deny|escalate"
    else:
        choices = "deny|escalate|mock"
    lines = [
        f"Child session {pending.child_id} is waiting for your approval.\n",
        f"Request: {req.request_id}\nTool: {req.tool_display_name or req.tool_name}\nInput:\n{shown}\n",
        f"Answer with: dispatch --resume {req.request_id} --outcome {choices} [--message TEXT]",
    ]
    if not pending.parent_may_approve:
        lines.append("Only the user can approve this (escalate).")
    if req.conducted:
        lines.append(
            "This tool reaches a system outside the sim, so the call does not run: "
            "answer with mock and the result the real system would give "
            "(use made-up IDs, never real ones)."
        )
    elif "mock" in choices:
        lines.append(
            "mock: add --result TEXT (and --error for a failure); the call does not run, "
            "and the child gets TEXT as its result."
        )
    lines.append("That call then waits on the child again.")
    return "\n".join(lines)
