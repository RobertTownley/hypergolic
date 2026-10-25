import asyncio
import logging
from typing import Any, Literal, cast

from anthropic.types import Message, MessageParam
from pydantic import BaseModel

from hypergolic.ids import new_id
from hypergolic.sessions import session_rows
from hypergolic.messages import message_rows
from hypergolic.config.settings import DEFAULT_STRIP_HISTORY_THINKING
from hypergolic.db.models import DBMessage
from hypergolic.messages.repair import repair_message_sequence, sanitize_tool_input
from hypergolic.messages.types import (
    ARTIFACT_MESSAGE_PREFIX,
    CONVERSATION_SUMMARY_PREFIX,
    TURN_SUMMARY_PREFIX,
    UNSUMMARIZED_CONTENT_PREFIX,
    EXCLUDED_CONTENT_FIELDS,
    EXCLUDED_FIELDS,
)
from hypergolic.harness.app.state import get_app

logger = logging.getLogger(__name__)


def strip_excluded_fields(content: list[Any]) -> list[Any]:
    cleaned = []
    for block in content:
        if isinstance(block, dict):
            cleaned.append(
                {k: v for k, v in block.items() if k not in EXCLUDED_CONTENT_FIELDS}
            )
        else:
            cleaned.append(block)
    return cleaned


THINKING_BLOCK_TYPES = frozenset({"thinking", "redacted_thinking"})
THINKING_ELIDED_STUB = "[thinking elided]"


def strip_thinking_blocks(messages: list[MessageParam]) -> list[MessageParam]:
    out: list[MessageParam] = []
    for msg in messages:
        content = msg.get("content")
        if msg["role"] != "assistant" or not isinstance(content, list):
            out.append(msg)
            continue
        kept = [
            b for b in content
            if not (isinstance(b, dict) and b.get("type") in THINKING_BLOCK_TYPES)
        ]
        if len(kept) == len(content):
            out.append(msg)
            continue
        if not kept:
            kept = [{"type": "text", "text": THINKING_ELIDED_STUB}]
        out.append(MessageParam(role=msg["role"], content=cast(Any, kept)))
    return out


def should_strip_thinking(role_id: str | None) -> bool:
    try:
        app = get_app()
    except RuntimeError:
        return DEFAULT_STRIP_HISTORY_THINKING
    role = app.get_role(role_id) if role_id is not None else None
    if role is not None and role.strip_history_thinking is not None:
        return role.strip_history_thinking
    return app.strip_history_thinking


_SYNTHESIZED_USER_PREFIXES = (
    CONVERSATION_SUMMARY_PREFIX,
    TURN_SUMMARY_PREFIX,
    UNSUMMARIZED_CONTENT_PREFIX,
    ARTIFACT_MESSAGE_PREFIX,
)


def is_user_authored(content: list[Any]) -> bool:
    has_content = False
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "tool_result":
            return False
        if btype == "text":
            if block.get("text", "").startswith(_SYNTHESIZED_USER_PREFIXES):
                return False
            has_content = True
        elif btype in ("image", "document"):
            has_content = True
    return has_content


def _project_survivors(
    rows: list[DBMessage],
) -> tuple[list[MessageParam], list[str | None]]:
    messages: list[MessageParam] = []
    message_ids: list[str | None] = []
    dropped_span = False
    for row in rows:
        if row.truncated and not (row.role == "user" and is_user_authored(row.content)):
            dropped_span = True
            continue
        content = strip_excluded_fields(row.content)
        if dropped_span and messages and messages[-1]["role"] == row.role == "user":
            merged = [*cast(list[Any], messages[-1]["content"]), *content]
            messages[-1] = MessageParam(role="user", content=cast(Any, merged))
        else:
            messages.append(
                MessageParam(
                    role=cast(Literal["user", "assistant", "system"], row.role),
                    content=content,
                )
            )
            message_ids.append(row.id)
        dropped_span = False
    return messages, message_ids


def load_session_messages(session_id: str) -> list[MessageParam]:
    messages, message_ids = _project_survivors(message_rows.for_session(session_id))
    session = session_rows.fetch(session_id)
    if should_strip_thinking(session.role if session else None):
        messages = strip_thinking_blocks(messages)
    return repair_message_sequence(messages, session_id=session_id, message_ids=message_ids)


async def persist_agent_message(session_id: str, message: Message) -> str:
    return await asyncio.to_thread(_persist_agent_message_sync, session_id, message)


def _persist_agent_message_sync(session_id: str, message: Message) -> str:
    content = []
    for block in message.content:
        if isinstance(block, BaseModel):
            dumped = block.model_dump(mode="json", exclude=EXCLUDED_FIELDS)
            if dumped.get("type") == "tool_use" and isinstance(dumped.get("input"), dict):
                dumped["input"] = sanitize_tool_input(dumped["input"])
            content.append(dumped)
        else:
            content.append(block)

    usage = message.usage.model_dump(mode="json") if message.usage else None

    db_message = DBMessage(
        id=new_id(),
        session_id=session_id,
        content=content,
        model=message.model,
        provider_message_id=message.id,
        role=message.role,
        stop_reason=message.stop_reason,
        stop_sequence=message.stop_sequence,
        usage=usage,
    )
    message_rows.insert(db_message)
    return db_message.id


def _normalize_content(message: MessageParam):
    content = message.get("content", [])
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    normalized = []
    for block in content:
        if isinstance(block, BaseModel):
            normalized.append(block.model_dump(mode="json"))
        else:
            normalized.append(block)
    return normalized


async def persist_messages(
    session_id: str,
    messages: list[MessageParam],
):
    if not messages:
        return
    await asyncio.to_thread(_persist_messages_sync, session_id, messages)


def _persist_messages_sync(
    session_id: str,
    messages: list[MessageParam],
) -> None:
    message_rows.insert(*(
        DBMessage(
            session_id=session_id,
            content=_normalize_content(message),
            role=message.get("role", "user"),
        )
        for message in messages
    ))
