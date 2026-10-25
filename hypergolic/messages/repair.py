"""Repair of malformed message data, at persist time and load time.

Persist time: tool inputs the API returned as JSON strings instead of parsed
objects. Load time: sequences the Claude API would reject — broken shapes arise
from crashes/restarts mid-turn (dangling tool_use), cancelled calls (orphaned
user turns), and summarization dropping a tool_use/tool_result pair's first
half. Load-time repairs are non-destructive: the DB rows are untouched and
fixes are re-derived on every load.
"""

import json
import logging
from typing import Any, cast

from anthropic.types import MessageParam

from hypergolic.messages.block_guards import is_tool_use_block
logger = logging.getLogger(__name__)

FORGOTTEN_STUB = "[forgotten]"


def _try_parse_json_string(value: str) -> list | dict | None:
    """Attempt to parse a string as a JSON array or object, stripping trailing garbage if needed."""
    try:
        parsed = json.loads(value)
        if isinstance(parsed, (list, dict)):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    closing = "]" if value.lstrip().startswith("[") else "}"
    last_close = value.rfind(closing)
    if last_close > 0:
        try:
            parsed = json.loads(value[: last_close + 1])
            if isinstance(parsed, (list, dict)):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def sanitize_tool_input(input_dict: dict[str, Any]) -> dict[str, Any]:
    """Fix tool input values that the API returned as JSON strings instead of parsed objects."""
    result = {}
    for key, value in input_dict.items():
        if isinstance(value, str) and value and value.lstrip()[:1] in ("[", "{"):
            parsed = _try_parse_json_string(value)
            if parsed is not None:
                logger.warning(
                    "Sanitized tool input key '%s': parsed string as %s",
                    key,
                    type(parsed).__name__,
                )
                result[key] = parsed
                continue
        result[key] = value
    return result


def _extract_tool_use_ids(msg: MessageParam) -> list[str]:
    content: Any = msg.get("content", [])
    if isinstance(content, str):
        return []
    return [
        str(block["id"])
        for block in content
        if is_tool_use_block(block) and block.get("id")
    ]


def _make_error_tool_results(tool_use_ids: list[str]) -> MessageParam:
    results: list[Any] = [
        {
            "type": "tool_result",
            "tool_use_id": tid,
            "content": [{"type": "text", "text": "Error: tool execution was interrupted by a prior failure"}],
            "is_error": True,
        }
        for tid in tool_use_ids
    ]
    return MessageParam(role="user", content=results)


def _to_block_list(content: Any) -> list[Any]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return list(content)


def _strip_orphan_tool_results(messages: list[MessageParam]) -> list[MessageParam]:
    """Drop tool_result blocks whose tool_use_id has no matching tool_use in the
    sequence. Orphans arise when a forgotten/summarized prefix is dropped outright
    and severs a tool_use from its result, which the Claude API rejects."""
    known = {
        b["id"]
        for msg in messages
        for b in _to_block_list(msg.get("content", []))
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id")
    }

    cleaned: list[MessageParam] = []
    for msg in messages:
        blocks = _to_block_list(msg.get("content", []))
        kept = [
            b
            for b in blocks
            if not (
                isinstance(b, dict)
                and b.get("type") == "tool_result"
                and b.get("tool_use_id") not in known
            )
        ]
        if len(kept) == len(blocks):
            cleaned.append(msg)
            continue
        if not kept:
            kept = [{"type": "text", "text": FORGOTTEN_STUB}]
        cleaned.append(MessageParam(role=msg["role"], content=cast(Any, kept)))
    return cleaned


def _stub_empty_content(messages: list[MessageParam]) -> list[MessageParam]:
    """Replace empty content (e.g. a pre-output refusal's ``content: []``) with a
    stub text block — the API rejects any replayed message with no content."""
    out: list[MessageParam] = []
    for msg in messages:
        blocks = [
            b
            for b in _to_block_list(msg.get("content", []))
            if not (isinstance(b, dict) and b.get("type") == "text" and not b.get("text"))
        ]
        if not blocks:
            logger.warning("Repairing empty-content %s message", msg["role"])
            msg = MessageParam(
                role=msg["role"],
                content=[{"type": "text", "text": "(empty message)"}],
            )
        out.append(msg)
    return out


def repair_message_sequence(
    messages: list[MessageParam],
    session_id: str | None = None,
    message_ids: list[str | None] | None = None,
) -> list[MessageParam]:
    """Fix broken message sequences that would cause Claude API errors.

    Handles three cases:
    1. Assistant tool_use message followed by another assistant message (no tool_results)
       → inserts synthetic error tool_results between them
    2. Assistant tool_use message at the end with no following tool_results
       → appends synthetic error tool_results
    3. Assistant tool_use message followed by a user message missing (some of) the
       matching tool_results — e.g. a restart while a tool call awaited approval,
       then a fresh user prompt → prepends synthetic error tool_results to it
    """
    if not messages:
        return messages

    messages = _stub_empty_content(_strip_orphan_tool_results(messages))

    ids = message_ids or [None] * len(messages)

    def _ctx(idx: int) -> str:
        parts: list[str] = []
        if session_id:
            parts.append(f"session={session_id}")
        if idx < len(ids) and ids[idx]:
            parts.append(f"message={ids[idx]}")
        return f" [{', '.join(parts)}]" if parts else ""

    repaired: list[MessageParam] = []
    repaired_idx: list[int] = []  # tracks original index for each entry in repaired
    for i, msg in enumerate(messages):
        if repaired and msg["role"] == "assistant" and repaired[-1]["role"] == "assistant":
            prev_tool_ids = _extract_tool_use_ids(repaired[-1])
            if prev_tool_ids:
                logger.warning(
                    "Repairing broken message sequence: inserting synthetic tool_results for %s%s",
                    prev_tool_ids,
                    _ctx(repaired_idx[-1]),
                )
                repaired.append(_make_error_tool_results(prev_tool_ids))
                repaired_idx.append(i)
            else:
                logger.warning(
                    "Repairing broken message sequence: merging consecutive assistant messages%s",
                    _ctx(i),
                )
                merged = _to_block_list(repaired[-1].get("content", [])) + _to_block_list(msg.get("content", []))
                repaired[-1] = MessageParam(role="assistant", content=merged)
                continue

        if repaired and msg["role"] == "user" and repaired[-1]["role"] == "assistant":
            prev_tool_ids = _extract_tool_use_ids(repaired[-1])
            if prev_tool_ids:
                blocks = _to_block_list(msg.get("content", []))
                present = {
                    b.get("tool_use_id")
                    for b in blocks
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                }
                missing = [tid for tid in prev_tool_ids if tid not in present]
                # Note: a real tool_result for a missing id in a *later* user message
                # would duplicate the synthetic after user-merge, but persist_messages
                # writes tool_results atomically in-batch so that shape can't occur.
                if missing:
                    logger.warning(
                        "Repairing broken message sequence: prepending synthetic tool_results for %s to user message%s",
                        missing,
                        _ctx(i),
                    )
                    synthetic = _to_block_list(_make_error_tool_results(missing).get("content", []))
                    msg = MessageParam(role="user", content=cast(Any, synthetic + blocks))

        if repaired and msg["role"] == "user" and repaired[-1]["role"] == "user":
            logger.warning(
                "Repairing broken message sequence: merging consecutive user messages%s",
                _ctx(i),
            )
            merged = _to_block_list(repaired[-1].get("content", [])) + _to_block_list(msg.get("content", []))
            repaired[-1] = MessageParam(role="user", content=merged)
            continue

        repaired.append(msg)
        repaired_idx.append(i)

    if repaired and repaired[-1]["role"] == "assistant":
        last_tool_ids = _extract_tool_use_ids(repaired[-1])
        if last_tool_ids:
            logger.warning(
                "Repairing broken message sequence: appending synthetic tool_results for trailing tool_use %s%s",
                last_tool_ids,
                _ctx(repaired_idx[-1]),
            )
            repaired.append(_make_error_tool_results(last_tool_ids))

    return repaired
