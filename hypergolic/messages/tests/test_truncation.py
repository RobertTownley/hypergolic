from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from anthropic.types import MessageParam, TextBlock

from hypergolic.db.models import DBMessage
from hypergolic.messages import message_rows
from hypergolic.messages.truncation import (
    FALLBACK_DIGEST_MAX_CHARS,
    FALLBACK_SUMMARY_HEADER,
    _fallback_summary_text,
    _get_threshold,
    mark_messages_truncated,
    should_truncate,
    truncate_with_summary,
)
from hypergolic.messages.types import CONVERSATION_SUMMARY_PREFIX
from tests._factories import build_assistant_message, build_session
from tests.conftest import make_message, make_project, make_session
from hypergolic.config.settings import DEFAULT_TRUNCATE_TOKEN_THRESHOLD

TRUNCATION = "hypergolic.messages.truncation"


def _msgs(*messages: Any) -> list[MessageParam]:
    return cast(list[MessageParam], list(messages))


def _text(text: str, role: str = "user") -> Any:
    return {"role": role, "content": [{"type": "text", "text": text}]}


def _seed_session(usage: dict | None = None) -> str:
    make_project("proj-1", "Test", "/tmp/test")
    sid = make_session("proj-1")
    make_message(sid, role="user", text="do the thing")
    make_message(sid, role="assistant", text="on it", model="m", usage=usage)
    return sid


def _first_text(row: DBMessage) -> str:
    return cast(dict, cast(list, row.content)[0])["text"]


def test_fallback_summary_keeps_recent_tail_and_warns():
    text = _fallback_summary_text(_msgs(_text("older"), _text("newest")))
    assert text.startswith(FALLBACK_SUMMARY_HEADER)
    assert text.index("older") < text.index("newest")


def test_fallback_summary_salvages_tail_of_oversized_message():
    big = "x" * FALLBACK_DIGEST_MAX_CHARS
    text = _fallback_summary_text(_msgs(_text("dropped"), _text(big)))
    assert "dropped" not in text
    assert text.count("x") == FALLBACK_DIGEST_MAX_CHARS
    assert len(text) <= len(FALLBACK_SUMMARY_HEADER) + FALLBACK_DIGEST_MAX_CHARS + 2


def test_fallback_summary_drops_oldest_when_budget_exhausted():
    big = "x" * (FALLBACK_DIGEST_MAX_CHARS - len("[user]: "))
    text = _fallback_summary_text(_msgs(_text("dropped"), _text(big)))
    assert "dropped" not in text
    assert big in text


def test_fallback_summary_with_no_content():
    assert _fallback_summary_text(_msgs()) == FALLBACK_SUMMARY_HEADER


def test_get_threshold_falls_back_to_default():
    with patch(f"{TRUNCATION}.get_app", side_effect=RuntimeError):
        assert _get_threshold() == DEFAULT_TRUNCATE_TOKEN_THRESHOLD


def test_get_threshold_prefers_app():
    with patch(f"{TRUNCATION}.get_app") as get_app:
        get_app.return_value.truncate_token_threshold = 123
        assert _get_threshold() == 123


@pytest.mark.parametrize("usage, expected", [
    (None, False),
    ({"input_tokens": 10}, False),
    ({"input_tokens": 5, "cache_read_input_tokens": 100_000}, True),
])
def test_should_truncate(usage, expected):
    sid = _seed_session(usage=usage)
    with patch(f"{TRUNCATION}._get_threshold", return_value=1000):
        assert should_truncate(sid) is expected


def test_should_truncate_without_messages():
    make_project("proj-1", "Test", "/tmp/test")
    assert should_truncate(make_session("proj-1")) is False


def test_mark_messages_truncated():
    sid = _seed_session()
    mark_messages_truncated(sid)
    assert all(row.truncated for row in message_rows.for_session(sid))


async def _truncate(sid: str, broadcast, summarize) -> None:
    session = build_session(sid=sid, project_id="proj-1", project_path="/tmp/test")
    with (
        patch(f"{TRUNCATION}.call_summarization_model", new=summarize),
        patch(f"{TRUNCATION}.set_session_status_and_broadcast", new=AsyncMock()),
    ):
        await truncate_with_summary(session, broadcast)


async def test_truncate_with_summary_inserts_summary(broadcast):
    sid = _seed_session()
    response = build_assistant_message(
        mid="summary-msg", content=[TextBlock(type="text", text="the summary")]
    )

    await _truncate(sid, broadcast, AsyncMock(return_value=response))

    rows = message_rows.for_session(sid)
    assert [row.truncated for row in rows[:2]] == [True, True]
    assert rows[-1].role == "user"
    assert _first_text(rows[-1]) == f"{CONVERSATION_SUMMARY_PREFIX}\n\nthe summary"
    assert not rows[-1].truncated
    assert broadcast.await_args.args[0].type == "truncated"


async def test_truncate_with_summary_falls_back_when_model_fails(broadcast):
    sid = _seed_session()

    await _truncate(sid, broadcast, AsyncMock(side_effect=ValueError("empty response")))

    rows = message_rows.for_session(sid)
    assert [row.truncated for row in rows[:2]] == [True, True]
    summary = _first_text(rows[-1])
    assert summary.startswith(CONVERSATION_SUMMARY_PREFIX)
    assert FALLBACK_SUMMARY_HEADER in summary
    assert "do the thing" in summary
    assert broadcast.await_args.args[0].type == "truncated"


async def test_truncate_with_summary_noop_without_messages(broadcast):
    make_project("proj-1", "Test", "/tmp/test")
    sid = make_session("proj-1")
    summarize = AsyncMock()

    await _truncate(sid, broadcast, summarize)

    assert summarize.await_count == 0
    assert message_rows.for_session(sid) == []
