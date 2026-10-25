import asyncio

from anthropic.types import Message, MessageParam, StopReason

from hypergolic.dispatch.lifecycle import auto_conclude_if_needed
from hypergolic.enums import SessionStatus
from hypergolic.messages.conversation.dispatch import dispatch_stop_reason
from hypergolic.messages.conversation.retry import stream_response
from hypergolic.messages.persistence import (
    load_session_messages,
    persist_agent_message,
    persist_messages,
)
from hypergolic.messages.truncation import should_truncate, truncate_with_summary
from hypergolic.messages.turn_compaction import (
    compaction_lock,
    schedule_turn_compaction,
)
from hypergolic.messages.types import BroadcastFn, UserInterrupt
from hypergolic.prompts.blocks import to_text_blocks
from hypergolic.prompts.builder import frozen_prompt_blocks, live_prompt_blocks
from hypergolic.schemas import Session
from hypergolic.sessions.description.generate import maybe_generate_description
from hypergolic.sessions.status import (
    TERMINAL_STATUSES,
    get_session_status,
    set_session_status_and_broadcast,
)
from hypergolic.tools.cmd import build_cmd_tool
from hypergolic.tools.handlers import ApprovalCallback
from hypergolic.tools.wire import wire_schemas


async def create_message(
    session: Session,
    message: MessageParam | None,
    broadcast: BroadcastFn,
    cancel_event: asyncio.Event | None = None,
    approval_callback: ApprovalCallback | None = None,
) -> Message:
    response: Message | None = None
    stop_reason: StopReason | None = None

    # One `cmd` tool ships over the wire, shaped once per turn from the session's
    # containers. Nothing activates and nothing is granted mid-session — enabling
    # an MCP server changes files in ``/tools``, not tool definitions — so the
    # schema is stable for the session and the cached prompt prefix survives.
    wire_tools = [build_cmd_tool(session)]
    schemas = wire_schemas(wire_tools)
    tool_display_names = {t.id: t.name for t in wire_tools}

    frozen = await frozen_prompt_blocks(session, persist=True)
    # ``None``: a resumed turn, or a caller (websocket connect) that already
    # persisted the user message before the turn started.
    async with compaction_lock(session.id):
        if message is not None:
            await persist_messages(session_id=session.id, messages=[message])
    if message is not None:
        await maybe_generate_description(session.id, broadcast)

    def _check_cancelled() -> None:
        if cancel_event and cancel_event.is_set():
            raise UserInterrupt()

    while stop_reason != "end_turn":
        _check_cancelled()

        if await asyncio.to_thread(should_truncate, session.id):
            await truncate_with_summary(session, broadcast)

        await set_session_status_and_broadcast(
            session.id, SessionStatus.THINKING, broadcast
        )

        messages = await asyncio.to_thread(load_session_messages, session.id)

        # Workflow state and sandbox context are rebuilt each iteration so a
        # state transition or a just-started sandbox reaches the next LLM turn.
        prompt = to_text_blocks(frozen + await live_prompt_blocks(session))

        # Pass None so stream_response resolves the client for this
        # session's model tier (per-tier provider selection).
        response = await stream_response(
            None, session, prompt, schemas,
            messages, broadcast, _check_cancelled,
            tool_display_names,
        )

        if response.stop_reason is None:
            raise RuntimeError(
                f"LLM provider returned a response with no stop_reason (id={response.id!r})"
            )
        stop_reason = response.stop_reason
        message_id = await persist_agent_message(session_id=session.id, message=response)

        await dispatch_stop_reason(
            stop_reason, response, message_id, wire_tools, session, broadcast,
            approval_callback, _check_cancelled, tool_display_names,
        )

        if await asyncio.to_thread(get_session_status, session.id) in TERMINAL_STATUSES:
            break

    assert response is not None
    if stop_reason == "end_turn":
        schedule_turn_compaction(session, broadcast)
    await auto_conclude_if_needed(session.id, session.parent_id, response, broadcast)
    return response
