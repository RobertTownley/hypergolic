from typing import Any

from anthropic import ParsedMessageStreamEvent
from anthropic.lib.streaming._types import ParsedContentBlockStopEvent
from anthropic.types import (
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
)

from hypergolic.messages.types import BroadcastEvent, BroadcastFn


async def handle_streaming_event(
    event: ParsedMessageStreamEvent,
    broadcast: BroadcastFn,
    session_id: str,
    tool_display_names: dict[str, str] | None = None,
) -> None:
    if isinstance(event, RawContentBlockStartEvent):
        block = event.content_block
        block_data: dict[str, Any] = {"type": block.type, "index": event.index}
        if block.type == "text":
            block_data["text"] = ""
        elif block.type == "thinking":
            block_data["thinking"] = ""
        elif block.type == "tool_use":
            tool_name = getattr(block, "name", "")
            block_data["type"] = "tool_call"
            block_data["id"] = getattr(block, "id", "")
            block_data["name"] = tool_name
            block_data["display_name"] = (tool_display_names or {}).get(tool_name, tool_name)
            block_data["input"] = {}
        await broadcast(
            BroadcastEvent(
                type="content_block_start",
                role="assistant",
                content=[block_data],
                session_id=session_id,
            )
        )
    elif isinstance(event, RawContentBlockDeltaEvent):
        delta = event.delta
        delta_data: dict[str, Any] = {"type": delta.type, "index": event.index}
        if delta.type == "text_delta":
            delta_data["text"] = getattr(delta, "text", "")
        elif delta.type == "input_json_delta":
            delta_data["partial_json"] = getattr(delta, "partial_json", "")
        elif delta.type == "thinking_delta":
            delta_data["thinking"] = getattr(delta, "thinking", "")
        elif delta.type == "signature_delta":
            # Opaque crypto blob for multi-turn continuity; the UI has no
            # use for it, so don't broadcast it.
            return
        await broadcast(
            BroadcastEvent(
                type="content_block_delta",
                role="assistant",
                content=[delta_data],
                session_id=session_id,
            )
        )
    elif isinstance(event, ParsedContentBlockStopEvent):
        await broadcast(
            BroadcastEvent(
                type="content_block_stop",
                role="assistant",
                content=[{"index": event.index}],
                session_id=session_id,
            )
        )
