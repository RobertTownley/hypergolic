"""Type guards for narrowing Anthropic SDK content blocks.

The Anthropic SDK types `ToolResultBlockParam.content` and related fields as
wide unions (text / image / document / search_result / tool_reference blocks
plus their `Block` counterparts). Structural narrowing on `block["type"]`
doesn't flow through TypedDict unions in most type checkers, so code that
peeks at `block["text"]` trips `invalid-key` / `not-subscriptable` errors.

These guards do the runtime check once and give the checker a `TypeGuard`
so downstream subscripting is well-typed. `iter_content_blocks` coerces the
messy `MessageParam["content"]` union (str | Iterable[block]) into a list
of dicts we can iterate over.
"""

from collections.abc import Iterable
from typing import Any, TypeGuard, cast

from anthropic.types import (
    TextBlockParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
)


def is_text_block(block: object) -> TypeGuard[TextBlockParam]:
    return isinstance(block, dict) and cast(dict[str, Any], block).get("type") == "text"


def is_tool_use_block(block: object) -> TypeGuard[ToolUseBlockParam]:
    return isinstance(block, dict) and cast(dict[str, Any], block).get("type") == "tool_use"


def is_tool_result_block(block: object) -> TypeGuard[ToolResultBlockParam]:
    return isinstance(block, dict) and cast(dict[str, Any], block).get("type") == "tool_result"


def iter_content_blocks(
    content: str | Iterable[Any] | None,
) -> list[dict[str, Any]]:
    """Normalize a `MessageParam["content"]` value into a list of block dicts.

    - `None` -> `[]`
    - `str`  -> `[{"type": "text", "text": <str>}]`
    - iterable -> list, keeping only dict entries (non-dict items are dropped
      since the rest of our code assumes TypedDict-shaped blocks).
    """
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [cast(dict[str, Any], b) for b in content if isinstance(b, dict)]
