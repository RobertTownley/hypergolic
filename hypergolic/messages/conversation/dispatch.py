import asyncio
from typing import Callable

from anthropic.types import Message, StopReason

from hypergolic.enums import SessionStatus
from hypergolic.messages.content_blocks import serialize_content_blocks
from hypergolic.messages.conversation.interrupts import persist_interrupt_tool_results
from hypergolic.messages.conversation.stop_reasons import handle_continue
from hypergolic.messages.persistence import persist_messages
from hypergolic.messages.types import BroadcastEvent, BroadcastFn, ModelRefusal, UserInterrupt
from hypergolic.schemas import Session
from hypergolic.sessions.status import set_session_status_and_broadcast
from hypergolic.tools.handlers import (
    ApprovalCallback,
    ToolUseResult,
    handle_tool_use,
)
from hypergolic.workflows.engine import (
    apply_pending_context_actions,
    discard_pending_context_actions,
)


async def handle_tool_use_stop(
    response: Message,
    tools: list,
    session: Session,
    broadcast: BroadcastFn,
    approval_callback: ApprovalCallback | None,
    check_cancelled: Callable[[], None],
) -> ToolUseResult:
    check_cancelled()
    await set_session_status_and_broadcast(
        session.id, SessionStatus.TOOL_USE, broadcast
    )
    tool_use_result = await handle_tool_use(
        agent_message=response,
        tools=tools,
        session=session,
        broadcast=broadcast,
        approval_callback=approval_callback,
    )
    check_cancelled()

    await persist_messages(
        session_id=session.id, messages=[tool_use_result.message]
    )
    raw_content = tool_use_result.message.get("content", [])
    await broadcast(
        BroadcastEvent(
            type="tool_result",
            role="user",
            content=serialize_content_blocks(raw_content),
            session_id=session.id,
        )
    )
    await apply_pending_context_actions(session, broadcast)
    return tool_use_result


def format_refusal_detail(response: Message) -> str:
    details = response.stop_details
    category = details.category if details else None
    explanation = details.explanation if details else None
    head = "Model refused to respond (provider safety classifier"
    head += f", category: {category})." if category else ")."
    parts = [head]
    if explanation:
        parts.append(explanation)
    parts.append(
        "Retrying unchanged will likely refuse again — rephrase, remove the "
        "triggering content, or switch models."
    )
    return " ".join(parts)


async def broadcast_response(
    response: Message, message_id: str, session_id: str, broadcast: BroadcastFn,
    tool_display_names: dict[str, str] | None = None,
) -> None:
    await broadcast(
        BroadcastEvent(
            type="assistant_message",
            role="assistant",
            content=serialize_content_blocks(response.content, tool_display_names),
            session_id=session_id,
            model=response.model,
            stop_reason=response.stop_reason,
            message_id=message_id,
            usage=(
                response.usage.model_dump(mode="json")
                if response.usage
                else None
            ),
        )
    )


async def dispatch_stop_reason(
    stop_reason: StopReason,
    response: Message,
    message_id: str,
    tools: list,
    session: Session,
    broadcast: BroadcastFn,
    approval_callback: ApprovalCallback | None,
    check_cancelled: Callable[[], None],
    tool_display_names: dict[str, str] | None = None,
) -> None:
    try:
        await broadcast_response(response, message_id, session.id, broadcast, tool_display_names)

        match stop_reason:
            case "end_turn":
                pass
            case "tool_use":
                await handle_tool_use_stop(
                    response, tools, session, broadcast,
                    approval_callback, check_cancelled,
                )
            case "max_tokens" | "pause_turn":
                await handle_continue(
                    stop_reason, session, broadcast, check_cancelled,
                    response=response,
                )
            case "refusal":
                raise ModelRefusal(format_refusal_detail(response))
            case _:
                raise Exception(f"Unhandled stop reason: {stop_reason}")
    except (UserInterrupt, asyncio.CancelledError):
        if stop_reason == "tool_use":
            discard_pending_context_actions(session.id)
            await persist_interrupt_tool_results(session.id, response)
        raise UserInterrupt()
    except Exception:
        # Generic exceptions intentionally do NOT synthesize tool_results here.
        # The load-time repair layer (repair_message_sequence) appends synthetic
        # error results for any orphaned tool_use on next turn load, so we can't
        # double up. Synthesizing here also used to mislabel crashes during the
        # post-tool_use refresh (e.g. broken MCP schemas) as "Interrupted by user".
        # We *do* drop any queued workflow context actions so a half-completed
        # transition doesn't leak truncation into the next turn.
        if stop_reason == "tool_use":
            discard_pending_context_actions(session.id)
        raise
