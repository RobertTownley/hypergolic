import json
from collections.abc import Iterable
from typing import Any


def serialize_text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def serialize_image_block(media_type: str, data: str) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def serialize_tool_call_block(
    id: str,
    name: str,
    input: dict[str, Any],
    display_name: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "tool_call",
        "id": id,
        "name": name,
        "display_name": display_name or name,
        "input": input,
    }


def serialize_tool_result_block(
    tool_use_id: str,
    content: list[dict[str, Any]],
    is_error: bool = False,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    block = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }
    if meta is not None:
        block["meta"] = meta
    return block


def serialize_anthropic_content_block(
    block: Any,
    tool_display_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    if hasattr(block, "model_dump"):
        dumped = block.model_dump(mode="json")
    elif isinstance(block, dict):
        dumped = dict(block)
    else:
        return {"type": "text", "text": str(block)}

    block_type = dumped.get("type", "")

    if block_type == "text":
        return serialize_text_block(dumped.get("text", ""))

    if block_type == "tool_use":
        name = dumped.get("name", "")
        display_name = (tool_display_names or {}).get(name, name) if tool_display_names else None
        raw_input = dumped.get("input", {})
        if isinstance(raw_input, str):
            try:
                raw_input = json.loads(raw_input)
            except (json.JSONDecodeError, ValueError):
                raw_input = {}
        return serialize_tool_call_block(
            id=dumped.get("id", ""),
            name=name,
            input=raw_input if isinstance(raw_input, dict) else {},
            display_name=display_name,
        )

    if block_type == "image":
        source = dumped.get("source", {})
        return serialize_image_block(
            media_type=source.get("media_type", ""),
            data=source.get("data", ""),
        )

    if block_type == "tool_result":
        raw_content = dumped.get("content", [])
        if isinstance(raw_content, str):
            raw_content = [{"type": "text", "text": raw_content}]
        elif isinstance(raw_content, list):
            raw_content = [
                serialize_anthropic_content_block(c)
                for c in raw_content
            ]
        return serialize_tool_result_block(
            tool_use_id=dumped.get("tool_use_id", ""),
            content=raw_content,
            is_error=dumped.get("is_error", False),
            meta=dumped.get("meta"),
        )

    return dumped


def serialize_content_blocks(
    blocks: str | Iterable[Any],
    tool_display_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(blocks, str):
        return [serialize_text_block(blocks)]
    return [
        serialize_anthropic_content_block(block, tool_display_names)
        for block in blocks
    ]
