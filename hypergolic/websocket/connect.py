import asyncio
import logging

from anthropic.types import MessageParam, TextBlockParam

from hypergolic.enums import SessionStatus
from hypergolic.messages.persistence import persist_messages
from hypergolic.messages.turn_compaction import compaction_lock
from hypergolic.messages.types import UNSUMMARIZED_CONTENT_PREFIX
from hypergolic.messages.types import BroadcastFn
from hypergolic.sessions.description.generate import maybe_generate_description
from hypergolic.sessions.operations import create_session, load_session
from hypergolic.sessions.status import set_session_status_and_broadcast
from hypergolic.tools.handlers import ApprovalCallback
from hypergolic.sessions.errors import format_error_detail, persist_error, persist_error_message
from hypergolic.websocket.helpers import build_content_blocks
from hypergolic.websocket.schemas import ConnectMessage
from hypergolic.sessions.turn import NotifyFn, run_session_turn
from hypergolic.telemetry.events import emit
from hypergolic.workflows.engine import activate_workflow, WorkflowError

logger = logging.getLogger(__name__)



def _user_messages(request: ConnectMessage) -> list[MessageParam]:
    """Recall blocks become their own synthesized message so a flatten can
    drop them without taking the user's words along."""
    recalls = [
        TextBlockParam(
            type="text",
            text=(
                f"{UNSUMMARIZED_CONTENT_PREFIX} The user re-included this "
                f"previously summarized content:\n\n{b['text']}"
            ),
        )
        for b in request.content_blocks or []
        if b.get("type") == "summary_recall" and b.get("text")
    ]
    messages: list[MessageParam] = []
    if recalls:
        messages.append({"role": "user", "content": recalls})
    messages.append({"role": "user", "content": build_content_blocks(request)})
    return messages

async def handle_connect(
    request: ConnectMessage,
    cancel_event: asyncio.Event,
    notify: NotifyFn,
    broadcast: BroadcastFn,
    approval_callback: ApprovalCallback,
) -> None:
    """Handle a new chat message: create/load session, optionally activate workflow, run turn."""
    session_id: str | None = None
    try:
        if request.session_id:
            session = await asyncio.to_thread(load_session, request.session_id)
        else:
            if not request.project_id:
                raise ValueError("project_id is required to create a new session")
            if not request.base_branch:
                raise ValueError("base_branch is required to create a new session")
            session = await asyncio.to_thread(
                create_session,
                project_id=request.project_id,
                base_branch=request.base_branch,
                model_tier=request.model_tier,
            )

        session_id = session.id
        emit(
            "message.sent", session_id=session_id, new_session=not request.session_id,
            chars=len(request.message), blocks=len(request.content_blocks or []),
            workflow=request.workflow_id,
        )

        if request.workflow_id:
            try:
                await activate_workflow(session, request.workflow_id, broadcast)
            except WorkflowError as wfe:
                await notify({"type": "error", "detail": str(wfe), "session_id": session.id})
                return

        messages = _user_messages(request)
        # Persist before turn setup: the interrupted turn's event triggers a
        # client refetch that must find this message.
        async with compaction_lock(session.id):
            await persist_messages(session_id=session.id, messages=messages)
        await maybe_generate_description(session.id, broadcast)

        await run_session_turn(
            session.id, None, cancel_event,
            notify, broadcast, approval_callback,
        )
    except Exception as exc:
        logger.error("Error during WebSocket turn", exc_info=True)
        detail = format_error_detail(exc)
        if session_id:
            await set_session_status_and_broadcast(session_id, SessionStatus.ERROR, broadcast)
            await asyncio.to_thread(persist_error_message, session_id, detail)
            await asyncio.to_thread(persist_error, session_id, exc)
        try:
            await notify({"type": "error", "detail": detail, "session_id": session_id})
        except Exception:
            logger.warning("Failed to send error payload to WebSocket", exc_info=True)
