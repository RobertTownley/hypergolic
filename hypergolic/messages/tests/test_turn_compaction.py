from typing import cast
from unittest.mock import AsyncMock, patch

from anthropic.types import TextBlock

from hypergolic import App
from hypergolic.messages import message_rows
from hypergolic.harness.app.state import app_context
from hypergolic.messages.persistence import load_session_messages
from hypergolic.messages.turn_compaction import (
    _compact_last_turn,
    _load_turn,
    _still_valid,
    schedule_turn_compaction,
)
from hypergolic.messages.types import TURN_SUMMARY_PREFIX
from tests._factories import build_assistant_message, build_session
from tests.conftest import make_message, make_project, make_session

COMPACTION = "hypergolic.messages.turn_compaction"

BIG = "x" * 30_000


def _tool_use(text: str = BIG) -> list:
    return [{"type": "tool_use", "id": "t1", "name": "cmd", "input": {"command": text}}]


def _tool_result(text: str = BIG) -> list:
    return [{"type": "tool_result", "tool_use_id": "t1", "content": text}]


def _seed_turn(interior_big: bool = True) -> str:
    make_project("proj-1", "Test", "/tmp/test")
    sid = make_session("proj-1")
    body = BIG if interior_big else "small"
    make_message(sid, role="user", text="do the thing")
    make_message(sid, role="assistant", content=_tool_use(body), stop_reason="tool_use")
    make_message(sid, role="user", content=_tool_result(body))
    make_message(sid, role="assistant", text="done", stop_reason="end_turn")
    return sid


async def _compact(sid: str, broadcast, summarize: AsyncMock) -> None:
    session = build_session(sid, project_id="proj-1")
    with patch(f"{COMPACTION}.call_summarization_model", summarize):
        await _compact_last_turn(session, broadcast)


def test_load_turn_slices_interior_only():
    sid = _seed_turn()
    turn = _load_turn(sid)
    assert turn is not None
    assert len(turn.interior_ids) == 2
    assert turn.chars > 50_000


def test_load_turn_messages_carry_retained_context():
    sid = _seed_turn()
    turn = _load_turn(sid)
    assert turn is not None
    assert len(turn.messages) == 4
    first, last = turn.messages[0], turn.messages[-1]
    assert first["role"] == "user"
    first_blocks = cast(list[dict], first["content"])
    assert first_blocks[0]["text"] == "[Retained: opening user message]"
    assert "do the thing" in str(first_blocks)
    assert last["role"] == "assistant"
    last_blocks = cast(list[dict], last["content"])
    assert last_blocks[0]["text"] == "[Retained: final reply]"
    assert "done" in str(last_blocks)


def test_load_turn_stops_at_prior_end_turn():
    sid = _seed_turn()
    make_message(sid, role="user", text="next question")
    make_message(sid, role="assistant", content=_tool_use(), stop_reason="tool_use")
    make_message(sid, role="user", content=_tool_result())
    make_message(sid, role="assistant", text="answered", stop_reason="end_turn")

    turn = _load_turn(sid)
    assert turn is not None
    assert len(turn.interior_ids) == 2
    rows = message_rows.for_session(sid)
    assert turn.interior_ids == [rows[5].id, rows[6].id]


def test_load_turn_none_when_last_is_not_end_turn():
    make_project("proj-1", "Test", "/tmp/test")
    sid = make_session("proj-1")
    make_message(sid, role="user", text="hi")
    make_message(sid, role="assistant", content=_tool_use(), stop_reason="tool_use")
    assert _load_turn(sid) is None


async def test_compact_inserts_summary_before_end_turn(broadcast):
    sid = _seed_turn()
    response = build_assistant_message(
        mid="sum-1", content=[TextBlock(type="text", text="did the thing")]
    )

    await _compact(sid, broadcast, AsyncMock(return_value=response))

    rows = message_rows.for_session(sid)
    assert [r.truncated for r in rows] == [False, True, True, False, False]
    summary, end_turn = rows[3], rows[4]
    assert summary.role == "user"
    assert cast(dict, summary.content[0])["text"] == f"{TURN_SUMMARY_PREFIX}\n\ndid the thing"
    assert end_turn.stop_reason == "end_turn"
    assert summary.sequence < end_turn.sequence
    assert broadcast.await_args.args[0].type == "truncated"

    visible = load_session_messages(sid)
    assert len(visible) == 2
    texts = [cast(dict, b)["text"] for b in cast(list, visible[0]["content"])]
    assert texts == ["do the thing", f"{TURN_SUMMARY_PREFIX}\n\ndid the thing"]


async def test_compact_skips_small_turns(broadcast):
    sid = _seed_turn(interior_big=False)
    summarize = AsyncMock()

    await _compact(sid, broadcast, summarize)

    summarize.assert_not_awaited()
    assert not any(r.truncated for r in message_rows.for_session(sid))


async def test_compact_keeps_raw_turn_when_model_fails(broadcast):
    sid = _seed_turn()

    await _compact(sid, broadcast, AsyncMock(side_effect=ValueError("boom")))

    assert not any(r.truncated for r in message_rows.for_session(sid))
    broadcast.assert_not_awaited()


def test_schedule_noop_when_disabled(broadcast):
    session = build_session("s-1")
    with app_context(App(turn_compaction_floor_tokens=0)):
        schedule_turn_compaction(session, broadcast)


def test_still_valid_tolerates_trailing_rows():
    sid = _seed_turn()
    turn = _load_turn(sid)
    assert turn is not None
    make_message(sid, role="user", text="user got here first")
    assert _still_valid(sid, turn)


def test_still_valid_false_after_flatten():
    sid = _seed_turn()
    turn = _load_turn(sid)
    assert turn is not None
    message_rows.truncate(sid)
    assert not _still_valid(sid, turn)


async def test_compact_shifts_trailing_rows_past_summary(broadcast):
    sid = _seed_turn()
    response = build_assistant_message(
        mid="sum-2", content=[TextBlock(type="text", text="did the thing")]
    )
    original = _compact_last_turn.__globals__["_load_turn"]

    def race_then_load(session_id: str):
        turn = original(session_id)
        make_message(sid, role="user", text="user got here first")
        return turn

    session = build_session(sid, project_id="proj-1")
    with (
        patch(f"{COMPACTION}.call_summarization_model", AsyncMock(return_value=response)),
        patch(f"{COMPACTION}._load_turn", race_then_load),
    ):
        await _compact_last_turn(session, broadcast)

    rows = message_rows.for_session(sid)
    roles = [(r.role, r.stop_reason) for r in rows[-3:]]
    assert roles == [("user", None), ("assistant", "end_turn"), ("user", None)]
    assert cast(dict, rows[-3].content[0])["text"].startswith(TURN_SUMMARY_PREFIX)
