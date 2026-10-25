import asyncio
import logging

from anthropic.types import MessageParam, TextBlockParam

from hypergolic.messages import message_rows
from hypergolic.config.settings import DEFAULT_TRUNCATE_TOKEN_THRESHOLD
from hypergolic.enums import SessionStatus
from hypergolic.harness.app.state import get_app
from hypergolic.messages.persistence import (
    load_session_messages,
    persist_agent_message,
    persist_messages,
)
from hypergolic.messages.summarization import (
    build_conversation_transcript,
    call_summarization_model,
    extract_summary_text,
)
from hypergolic.messages.types import (
    BroadcastEvent,
    BroadcastFn,
    CONVERSATION_SUMMARY_PREFIX,
)
from hypergolic.schemas import Session
from hypergolic.sessions.status import set_session_status_and_broadcast

logger = logging.getLogger(__name__)


FALLBACK_DIGEST_MAX_CHARS = 20_000

FALLBACK_SUMMARY_HEADER = (
    "Automatic summarization of the earlier conversation failed, so the "
    "history below is a raw transcript tail, not a summary. Older turns are "
    "gone. Re-read any file or command output you need instead of trusting "
    "recollection, and ask the user if the goal is unclear."
)


def _fallback_summary_text(messages: list[MessageParam]) -> str:
    tail: list[str] = []
    remaining = FALLBACK_DIGEST_MAX_CHARS
    for block in reversed(build_conversation_transcript(messages)):
        text = block["text"]
        if len(text) > remaining:
            if remaining > 0:
                tail.append(text[-remaining:])
            break
        tail.append(text)
        remaining -= len(text)
    return "\n\n".join([FALLBACK_SUMMARY_HEADER, *reversed(tail)])


def _get_threshold() -> int:
    try:
        return get_app().truncate_token_threshold
    except RuntimeError:
        return DEFAULT_TRUNCATE_TOKEN_THRESHOLD


def should_truncate(session_id: str) -> bool:
    row = message_rows.last(session_id, role="assistant")
    if row is None or row.usage is None:
        return False
    input_tokens = (
        row.usage.get("input_tokens", 0)
        + row.usage.get("cache_read_input_tokens", 0)
        + row.usage.get("cache_creation_input_tokens", 0)
    )
    return input_tokens > _get_threshold()


def mark_messages_truncated(session_id: str) -> None:
    message_rows.truncate(session_id)


async def truncate_with_summary(
    session: Session, broadcast: BroadcastFn
) -> None:
    logger.info("Summarizing and truncating conversation for session %s", session.id)

    await set_session_status_and_broadcast(
        session.id, SessionStatus.TRUNCATING, broadcast
    )

    messages = await asyncio.to_thread(load_session_messages, session.id)
    if not messages:
        return

    try:
        response = await call_summarization_model(session.model_tier, messages)
    except Exception:
        logger.exception(
            "Summarization failed for session %s; falling back to a raw "
            "transcript tail",
            session.id,
        )
        summary_body = _fallback_summary_text(messages)
    else:
        await persist_agent_message(session_id=session.id, message=response)
        summary_body = extract_summary_text(response)
    summary_text = f"{CONVERSATION_SUMMARY_PREFIX}\n\n{summary_body}"

    await asyncio.to_thread(mark_messages_truncated, session.id)

    summary_message = MessageParam(
        role="user",
        content=[TextBlockParam(type="text", text=summary_text)],
    )
    await persist_messages(session_id=session.id, messages=[summary_message])

    logger.info("Conversation truncated for session %s", session.id)

    await broadcast(
        BroadcastEvent(
            type="truncated",
            role="system",
            content=[],
            session_id=session.id,
        )
    )
