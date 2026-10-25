from typing import Any

from anthropic.types import DocumentBlockParam, ImageBlockParam, TextBlockParam
from pydantic import BaseModel

from hypergolic.messages.types import BroadcastEvent
from hypergolic.websocket.schemas import ConnectMessage


def serialize_event(event: BroadcastEvent) -> dict[str, Any]:
    content = []
    for block in event.content:
        if isinstance(block, BaseModel):
            content.append(block.model_dump(mode="json"))
        elif isinstance(block, dict):
            content.append(block)
        else:
            content.append(str(block))

    payload: dict[str, Any] = {
        "type": event.type,
        "role": event.role,
        "content": content,
    }
    if event.session_id:
        payload["session_id"] = event.session_id
    if event.model:
        payload["model"] = event.model
    if event.stop_reason:
        payload["stop_reason"] = event.stop_reason
    if event.message_id:
        payload["message_id"] = event.message_id
    if event.usage:
        payload["usage"] = event.usage
    return payload


def build_content_blocks(
    request: ConnectMessage,
) -> list[TextBlockParam | ImageBlockParam | DocumentBlockParam]:
    blocks: list[TextBlockParam | ImageBlockParam | DocumentBlockParam] = []
    if request.content_blocks:
        for raw_block in request.content_blocks:
            if raw_block.get("type") == "image" and "source" in raw_block:
                blocks.append(ImageBlockParam(type="image", source=raw_block["source"]))
            elif raw_block.get("type") == "document" and "source" in raw_block:
                blocks.append(DocumentBlockParam(type="document", source=raw_block["source"]))
            elif raw_block.get("type") == "text" and "text" in raw_block:
                blocks.append(TextBlockParam(type="text", text=raw_block["text"]))
    blocks.append(TextBlockParam(type="text", text=request.message))
    return blocks
