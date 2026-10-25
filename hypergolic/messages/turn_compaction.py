import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal, cast

from anthropic.types import MessageParam

from hypergolic.messages import message_rows
from hypergolic.config.settings import (
    DEFAULT_TURN_COMPACTION_FLOOR_TOKENS,
    PROMPTS_DIR,
)
from hypergolic.harness.app.state import get_app
from hypergolic.db.models import DBMessage
from hypergolic.messages.summarization import (
    call_summarization_model,
    extract_summary_text,
)
from hypergolic.messages.types import (
    BroadcastEvent,
    BroadcastFn,
    TURN_SUMMARY_PREFIX,
)
from hypergolic.schemas import Session

logger = logging.getLogger(__name__)

COMPACT_TURN_PROMPT_PATH = PROMPTS_DIR / "compact_turn_prompt.md"
COMPACT_TURN_MAX_TOKENS = 1024
APPROX_CHARS_PER_TOKEN = 4

_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_tasks: dict[str, asyncio.Task] = {}


@dataclass
class TurnSlice:
    interior_ids: list[str]
    messages: list[MessageParam]
    end_turn_id: str
    end_turn_seq: int
    chars: int


def compaction_lock(session_id: str) -> asyncio.Lock:
    return _locks[session_id]


def _floor_tokens() -> int:
    try:
        return get_app().turn_compaction_floor_tokens
    except RuntimeError:
        return DEFAULT_TURN_COMPACTION_FLOOR_TOKENS


def schedule_turn_compaction(session: Session, broadcast: BroadcastFn) -> None:
    if _floor_tokens() <= 0:
        return
    task = asyncio.create_task(_compact_last_turn(session, broadcast))
    _tasks[session.id] = task

    def _forget(done: asyncio.Task) -> None:
        if _tasks.get(session.id) is done:
            del _tasks[session.id]

    task.add_done_callback(_forget)


def _is_interior(row: DBMessage) -> bool:
    if row.truncated:
        return False
    if row.role == "assistant":
        return row.stop_reason != "end_turn"
    if row.role != "user":
        return False
    return any(
        isinstance(b, dict) and b.get("type") == "tool_result"
        for b in row.content
    )


def _retained(label: str, row: DBMessage) -> MessageParam:
    marker = {"type": "text", "text": f"[Retained: {label}]"}
    return MessageParam(
        role=cast(Literal["user", "assistant"], row.role),
        content=cast(Any, [marker, *row.content]),
    )


def _slice_turn(rows: list[DBMessage]) -> TurnSlice | None:
    last = rows[-1] if rows else None
    if last is None or last.role != "assistant" or last.stop_reason != "end_turn":
        return None
    interior = []
    for row in reversed(rows[:-1]):
        if not _is_interior(row):
            break
        interior.append(row)
    if not interior:
        return None
    interior.reverse()
    messages = [
        MessageParam(
            role=cast(Literal["user", "assistant"], r.role),
            content=cast(Any, r.content),
        )
        for r in interior
    ]
    opening_idx = len(rows) - 2 - len(interior)
    if opening_idx >= 0:
        opening = rows[opening_idx]
        if opening.role == "user" and not opening.truncated:
            messages.insert(0, _retained("opening user message", opening))
    messages.append(_retained("final reply", last))
    return TurnSlice(
        interior_ids=[r.id for r in interior],
        messages=messages,
        end_turn_id=last.id,
        end_turn_seq=last.sequence,
        chars=sum(len(json.dumps(r.content)) for r in interior),
    )


def _load_turn(session_id: str) -> TurnSlice | None:
    return _slice_turn(message_rows.for_session(session_id))


def _still_valid(session_id: str, turn: TurnSlice) -> bool:
    rows = {r.id: r for r in message_rows.for_session(session_id)}
    end = rows.get(turn.end_turn_id)
    flattened = any(rows[i].truncated for i in turn.interior_ids if i in rows)
    return end is not None and end.sequence == turn.end_turn_seq and not flattened


def _apply(session_id: str, turn: TurnSlice, summary_text: str) -> None:
    message_rows.splice(session_id, turn.interior_ids, DBMessage(
        session_id=session_id, content=[{"type": "text", "text": summary_text}],
        role="user", sequence=turn.end_turn_seq,
    ))


async def _compact_last_turn(session: Session, broadcast: BroadcastFn) -> None:
    turn = await asyncio.to_thread(_load_turn, session.id)
    floor = _floor_tokens()
    if turn is None or turn.chars < floor * APPROX_CHARS_PER_TOKEN:
        return
    try:
        response = await call_summarization_model(
            session.model_tier,
            turn.messages,
            COMPACT_TURN_PROMPT_PATH,
            closing="Compact this turn now.",
            max_tokens=COMPACT_TURN_MAX_TOKENS,
        )
    except Exception:
        logger.exception(
            "Turn compaction failed for session %s; keeping the raw turn",
            session.id,
        )
        return
    summary = f"{TURN_SUMMARY_PREFIX}\n\n{extract_summary_text(response)}"
    async with compaction_lock(session.id):
        if not await asyncio.to_thread(_still_valid, session.id, turn):
            logger.info(
                "Turn compaction superseded for session %s; keeping the raw turn",
                session.id,
            )
            return
        await asyncio.to_thread(_apply, session.id, turn, summary)
    await broadcast(
        BroadcastEvent(
            type="truncated", role="system", content=[], session_id=session.id
        )
    )
