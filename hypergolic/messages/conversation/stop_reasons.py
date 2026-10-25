"""Handlers for non-standard stop reasons that continue the conversation loop."""

from typing import Any, Callable

from anthropic.types import (
    Message,
    MessageParam,
    TextBlockParam,
    ToolResultBlockParam,
    ToolUseBlock,
)

from hypergolic.messages.persistence import persist_messages
from hypergolic.messages.types import BroadcastEvent, BroadcastFn
from hypergolic.schemas import Session

CONTINUE_MESSAGES: dict[str, str] = {
    "max_tokens": (
        "Your previous response was cut off because it hit the max_tokens limit. "
        "Please continue where you left off. If you were writing a large output, "
        "consider breaking it into smaller pieces."
    ),
    "pause_turn": (
        "Your previous response was paused (pause_turn). "
        "Please continue where you left off."
    ),
}

TRUNCATED_TOOL_USE_ERROR = (
    "Error: this tool call was truncated by max_tokens before completion. "
    "The call was never executed. You may retry."
)


def _build_truncated_tool_results(response: Message) -> list[ToolResultBlockParam]:
    """Build error tool_result blocks for any tool_use blocks in a truncated response."""
    tool_blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]
    return [
        ToolResultBlockParam(
            type="tool_result",
            tool_use_id=b.id,
            content=[TextBlockParam(type="text", text=TRUNCATED_TOOL_USE_ERROR)],
            is_error=True,
        )
        for b in tool_blocks
    ]


async def handle_continue(
    stop_reason: str,
    session: Session,
    broadcast: BroadcastFn,
    check_cancelled: Callable[[], None],
    response: Message | None = None,
) -> None:
    """Inject a continuation prompt so the conversation loop keeps going.

    If the truncated response contained tool_use blocks, synthetic error
    tool_result blocks are included so the API doesn't reject the next
    request for missing tool_results.
    """
    check_cancelled()
    text = CONTINUE_MESSAGES[stop_reason]

    content: list[Any] = []
    if response is not None:
        content.extend(_build_truncated_tool_results(response))
    content.append({"type": "text", "text": text})

    continuation: MessageParam = {
        "role": "user",
        "content": content,
    }
    await persist_messages(session_id=session.id, messages=[continuation])
    await broadcast(
        BroadcastEvent(
            type="tool_result",
            role="user",
            content=content,
            session_id=session.id,
        )
    )
