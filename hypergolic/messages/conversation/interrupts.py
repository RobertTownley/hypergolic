import asyncio
from typing import Any

from anthropic.types import (
    Message,
    MessageParam,
    TextBlockParam,
    ToolResultBlockParam,
    ToolUseBlock,
)

from hypergolic.messages import message_rows
from hypergolic.db.models import DBMessage
from hypergolic.messages.persistence import persist_messages
from hypergolic.messages.types import INTERRUPTED_SUFFIX


def _extract_partial_text(stream: Any) -> str | None:
    try:
        snapshot = stream.current_message_snapshot
    except Exception:
        return None
    if not snapshot or not snapshot.content:
        return None
    text_parts = [
        block.text
        for block in snapshot.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    return "\n\n".join(text_parts) if text_parts else None


async def _persist_partial_assistant_message(session_id: str, text: str) -> None:
    await asyncio.to_thread(message_rows.insert, DBMessage(
        session_id=session_id,
        content=[{"type": "text", "text": text + INTERRUPTED_SUFFIX}],
        role="assistant",
        stop_reason="interrupted",
    ))


def _build_interrupt_tool_results(response: Message) -> MessageParam | None:
    tool_blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]
    if not tool_blocks:
        return None
    result_blocks: list[ToolResultBlockParam] = [
        ToolResultBlockParam(
            tool_use_id=b.id,
            type="tool_result",
            content=[TextBlockParam(type="text", text="Interrupted by user")],
            is_error=True,
        )
        for b in tool_blocks
    ]
    return MessageParam(role="user", content=result_blocks)


async def persist_interrupt_tool_results(session_id: str, response: Message) -> None:
    interrupt_result = _build_interrupt_tool_results(response)
    if interrupt_result:
        await persist_messages(session_id=session_id, messages=[interrupt_result])
