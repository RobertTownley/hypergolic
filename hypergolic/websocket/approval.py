import asyncio
import logging
import time
from typing import Any

from hypergolic.enums import SessionStatus
from hypergolic.sessions.status import set_session_status_and_broadcast
from hypergolic.messages.types import BroadcastFn
from hypergolic.telemetry.events import emit
from hypergolic.tools import approval_delegate
from hypergolic.tools.handlers import (
    AnnotationItem,
    ApprovalRequest,
    ApprovalResponse,
)
from hypergolic.websocket.hub import ConnectionHub
from hypergolic.websocket.turn_manager import TurnManager
from hypergolic.websocket.schemas import ApprovalResponseMessage

logger = logging.getLogger(__name__)


def build_approval_callback(
    hub: ConnectionHub,
    tm: TurnManager,
    broadcast: BroadcastFn,
):
    """Return an async approval_callback fanning out via the hub.

    The request payload is kept in ``tm.approval_payloads`` until resolved so
    a reconnecting client gets the approval card re-sent (see the router).
    A ``delegated`` request goes to the child's parent first (see
    :mod:`hypergolic.tools.approval_delegate`); the parent may hand it back
    to the human.
    """

    async def approval_callback(req: ApprovalRequest) -> ApprovalResponse:
        if req.delegated:
            return await approval_delegate.ask(req, ask_human)
        return await ask_human(req)

    async def ask_human(req: ApprovalRequest) -> ApprovalResponse:
        if req.session_id:
            await set_session_status_and_broadcast(
                req.session_id, SessionStatus.AWAITING_APPROVAL, broadcast,
            )
        payload: dict[str, Any] = {
            "type": "tool_approval_request",
            "tool_use_id": req.request_id,
            "tool_name": req.tool_name,
            "tool_display_name": req.tool_display_name or req.tool_name,
            "tool_input": req.tool_input,
            "session_id": req.session_id,
        }
        if req.approval_view is not None:
            payload["approval_view"] = req.approval_view.to_dict()
        await hub.send(payload)
        emit(
            "approval.requested", session_id=req.session_id, tool=req.tool_name,
            request_id=req.request_id, delegated=req.delegated,
        )
        started = time.monotonic()

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalResponse] = loop.create_future()
        tm.pending_approvals[req.request_id] = (req.session_id or "", future)
        tm.approval_payloads[req.request_id] = payload

        try:
            response = await future
            emit(
                "approval.replied", session_id=req.session_id, tool=req.tool_name,
                request_id=req.request_id, approved=response.approved,
                wait_s=round(time.monotonic() - started, 1),
                reason=bool(response.denial_reason),
                annotations=len(response.annotations or []),
            )
            if req.session_id:
                await set_session_status_and_broadcast(
                    req.session_id, SessionStatus.TOOL_USE, broadcast,
                )
            return response
        finally:
            tm.pending_approvals.pop(req.request_id, None)
            tm.approval_payloads.pop(req.request_id, None)

    return approval_callback


def resolve_approval_response(
    msg: ApprovalResponseMessage,
    tm: TurnManager,
) -> None:
    """Resolve a pending approval future from a client message."""
    entry = tm.pending_approvals.get(msg.tool_use_id)
    if not entry:
        logger.warning(
            "Dropping approval response for unknown request %s "
            "(approved=%s, %d annotations) — the pending request is gone, "
            "likely resolved already or lost to a server restart",
            msg.tool_use_id, msg.approved, len(msg.annotations or []),
        )
        emit(
            "approval.reply_dropped", request_id=msg.tool_use_id, approved=msg.approved,
        )
        return
    _sid, future = entry
    if future.done():
        return
    annotations = None
    if msg.annotations:
        annotations = [
            AnnotationItem(
                highlighted_text=a.highlighted_text,
                comment=a.comment,
            )
            for a in msg.annotations
        ]
    future.set_result(ApprovalResponse(
        approved=msg.approved,
        denial_reason=msg.denial_reason,
        annotations=annotations,
    ))
