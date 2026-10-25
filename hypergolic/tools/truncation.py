"""Tool output truncation and result block helpers."""

import logging
from typing import Any, cast

from anthropic.types import ToolResultBlockParam
from anthropic.types.tool_result_block_param import Content

from hypergolic.harness.primitives.results import ToolResult

logger = logging.getLogger(__name__)

MAX_TOOL_OUTPUT_CHARS = 80_000


def result_block(tool_use_id: str, output: ToolResult) -> ToolResultBlockParam:
    """Build a ToolResultBlockParam from a ToolResult."""
    block = ToolResultBlockParam(
        tool_use_id=tool_use_id,
        type="tool_result",
        content=cast('list[Content]', output.content),
        is_error=output.is_error,
    )
    if output.meta is not None:
        # Stored and broadcast, stripped on load. See EXCLUDED_CONTENT_FIELDS.
        cast('dict[str, Any]', block)["meta"] = output.meta
    return block


def truncate_tool_output(output: ToolResult, limit: int = MAX_TOOL_OUTPUT_CHARS) -> ToolResult:
    """Truncate tool output if total text chars exceed *limit*."""
    total_chars = output.total_text_chars()

    if total_chars <= limit:
        return output

    truncated_content: list[dict] = []
    remaining = limit

    for block in output.content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if len(text) <= remaining:
                truncated_content.append(block)
                remaining -= len(text)
            elif remaining > 0:
                truncated_content.append({"type": "text", "text": text[:remaining]})
                remaining = 0
        else:
            truncated_content.append(block)

    truncated_content.append({
        "type": "text",
        "text": f"\n\n[Output truncated: {total_chars:,} chars exceeded {limit:,} char limit. Request smaller ranges or more specific queries.]",
    })

    logger.warning("Tool output truncated: %s chars -> %s char limit", total_chars, limit)

    return ToolResult(content=truncated_content, is_error=output.is_error, meta=output.meta)
