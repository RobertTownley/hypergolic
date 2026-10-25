import asyncio
import logging
import uuid

from anthropic.types import MessageParam
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hypergolic.auth import readonly_session, verify_token
from hypergolic.dispatch.lifecycle import cancel_child_dispatches
from hypergolic.dispatch.state import register_turn_runner
from hypergolic.messages.types import BroadcastEvent
from hypergolic.websocket.approval import build_approval_callback, resolve_approval_response
from hypergolic.websocket.conclude import handle_conclude_session
from hypergolic.websocket.connect import handle_connect
from hypergolic.websocket.helpers import serialize_event
from hypergolic.websocket.hub import get_hub
from hypergolic.websocket.resume import resume_interrupted_sessions
from hypergolic.websocket.schemas import (
    ApprovalResponseMessage,
    ConcludeSessionMessage,
    ConnectMessage,
    WsClientMessage,
    parse_client_message,
)
from hypergolic.sessions.turn import run_session_turn
from hypergolic.telemetry.tracing import tracer
from hypergolic.websocket.turn_manager import TurnManager, get_turn_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def broadcast(event: BroadcastEvent) -> None:
    await get_hub().send(serialize_event(event))


approval_callback = build_approval_callback(get_hub(), get_turn_manager(), broadcast)


def start_turn(session_id: str, message: MessageParam | None) -> None:
    """Run a turn as a process-owned task; output fans out via the hub."""
    async def _turn_coro(cancel_event: asyncio.Event) -> None:
        await run_session_turn(
            session_id, message, cancel_event,
            get_hub().send, broadcast, approval_callback,
        )

    get_turn_manager().start_turn(session_id, _turn_coro)


register_turn_runner(start_turn)


class _SessionScopedSender:
    def __init__(self, ws: WebSocket, session_id: str):
        self._ws = ws
        self._session_id = session_id

    async def send_json(self, data: dict) -> None:
        if data.get("session_id") == self._session_id:
            await self._ws.send_json(data)


async def _handle_message(msg: WsClientMessage, ws: WebSocket, tm: TurnManager) -> None:
    if isinstance(msg, ApprovalResponseMessage):
        resolve_approval_response(msg, tm)
        return

    if isinstance(msg, ConcludeSessionMessage):
        await handle_conclude_session(msg, ws, tm, broadcast)
        return

    request = msg
    # New sessions get a unique placeholder key: with a global
    # manager, a shared "__new__" would let one tab's new-session
    # turn cancel another's.
    target_session_id = request.session_id or f"__new__{uuid.uuid4().hex}"

    await cancel_child_dispatches(target_session_id)
    await tm.cancel_existing_turn(target_session_id)

    async def _bound_run_turn(cancel_event: asyncio.Event, req: ConnectMessage = request) -> None:
        await handle_connect(
            req, cancel_event,
            get_hub().send, broadcast, approval_callback,
        )

    tm.start_turn(target_session_id, _bound_run_turn)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    token = ws.cookies.get("h_token", "")
    # Spectator: hub broadcasts only. Every inbound message is dropped — a
    # read-only client must never resolve approvals or start turns — and the
    # connect-time resume side effect stays with the real client.
    spectator = not verify_token(token)
    scoped_session = readonly_session(token) if spectator else None
    if spectator and scoped_session is None:
        await ws.close(code=4003, reason="Unauthorized")
        return
    await ws.accept()
    hub = get_hub()
    tm = get_turn_manager()
    # A spectator's token is scoped to one session; it observes that session's
    # events and nothing else (session-less events included: they are control
    # signals for real clients).
    sender = _SessionScopedSender(ws, scoped_session) if scoped_session else ws
    hub.attach(sender)

    try:
        # Re-send in-flight approval cards so a reloaded client can respond.
        for payload in list(tm.approval_payloads.values()):
            await sender.send_json(payload)

        if not spectator:
            with tracer.start_as_current_span("ws.resume_sessions"):
                await resume_interrupted_sessions(start_turn)

        while True:
            raw = await ws.receive_json()
            if spectator:
                logger.warning("Dropping message from read-only websocket client")
                continue
            msg = parse_client_message(raw)
            # One short trace per inbound message; turns it starts are their
            # own traces (see root_span) linked back here.
            with tracer.start_as_current_span(
                "ws.message", attributes={"ws.message.type": type(msg).__name__},
            ) as span:
                session_id = getattr(msg, "session_id", None)
                if session_id:
                    span.set_attribute("session.id", session_id)
                await _handle_message(msg, ws, tm)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        logger.error("Unexpected WebSocket error", exc_info=True)
    finally:
        # Detach only. Turns belong to the process, not this socket: a page
        # reload or network blip must never interrupt other sessions' work.
        hub.detach(sender)
        try:
            await ws.close()
        except Exception:
            logger.debug("Failed to close WebSocket cleanly", exc_info=True)
