from tests.conftest import make_message, make_session
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hypergolic.sessions.description.generate import (
    DESCRIPTION_CHAR_THRESHOLD,
    _generate_description,
    _get_dispatch_prompt,
    maybe_generate_description,
)
from hypergolic.sessions.description.store import (
    get_session_description,
    save_description,
)
from hypergolic.sessions.description.text import (
    count_user_text_chars,
    extract_text,
    get_user_text_preview,
)


def test_count_user_text_chars_counts_only_visible_user_text():
    make_session(sid="s1")
    make_message("s1", "user", "hello world")
    make_message("s1", "assistant", "long assistant response here")
    make_message("s1", "user", "hidden", truncated=True)
    make_message("s1", "user", content=[
        {"type": "text", "text": "abc"},
        {"type": "tool_result", "tool_use_id": "t1", "content": "big data"},
    ])
    make_message("s1", "user", content="raw string")

    assert count_user_text_chars("s1") == 11 + 3 + 10


def test_extract_text_returns_empty_for_unexpected_types():
    assert extract_text(12345) == ""
    assert extract_text(None) == ""


def test_save_and_get_description():
    make_session(sid="s1")
    assert get_session_description("s1") is None
    save_description("s1", "my description")
    assert get_session_description("s1") == "my description"


def test_get_user_text_preview_joins_user_text_and_truncates():
    make_session(sid="s1")
    make_message("s1", "user", "first message")
    make_message("s1", "assistant", "ignored")
    make_message("s1", "user", content="raw string msg")
    make_message("s1", "user", "x" * 3000)

    preview = get_user_text_preview("s1")
    assert "first message" in preview
    assert "raw string msg" in preview
    assert "ignored" not in preview
    assert len(preview) == 2000


async def test_generate_description_persists_and_broadcasts(broadcast):
    make_session(sid="s1")
    make_message("s1", "user", "I want to build a session description feature")

    with patch("hypergolic.sessions.description.generate.generate_text", new=AsyncMock(return_value="Session description feature")):
        await _generate_description("s1", broadcast)

    assert get_session_description("s1") == "Session description feature"
    broadcast.assert_called_once()
    event = broadcast.call_args[0][0]
    assert event.type == "session_description_update"
    assert event.session_id == "s1"
    assert event.content == [{"description": "Session description feature"}]


@pytest.mark.parametrize("raw, expected", [
    ('"Session description feature"', "Session description feature"),
    ("- Fix list pagination", "Fix list pagination"),
])
async def test_generate_description_strips_model_artifacts(broadcast, raw, expected):
    make_session(sid="s1")
    make_message("s1", "user", "some user content")

    with patch("hypergolic.sessions.description.generate.generate_text", new=AsyncMock(return_value=raw)):
        await _generate_description("s1", broadcast)

    assert get_session_description("s1") == expected


async def test_generate_description_keeps_first_line_only(broadcast):
    make_session(sid="s1")
    make_message("s1", "user", "some user content")

    with patch("hypergolic.sessions.description.generate.generate_text", new=AsyncMock(return_value="Fix pagination\nThe session covers...")):
        await _generate_description("s1", broadcast)

    assert get_session_description("s1") == "Fix pagination"


@pytest.mark.parametrize("has_message, generate_mock", [
    (True, AsyncMock(return_value='""')),
    (True, AsyncMock(return_value="I need to access the session data first to understand what was discussed before I can label it.")),
    (False, AsyncMock(return_value="anything")),
    (True, AsyncMock(return_value=None)),
    (True, AsyncMock(side_effect=RuntimeError("API down"))),
])
async def test_generate_description_noops(broadcast, has_message, generate_mock):
    make_session(sid="s1")
    if has_message:
        make_message("s1", "user", "some content")

    with patch("hypergolic.sessions.description.generate.generate_text", new=generate_mock):
        await _generate_description("s1", broadcast)

    assert get_session_description("s1") is None
    broadcast.assert_not_called()


@pytest.mark.parametrize("existing_description, chars", [
    ("already set", 200),
    (None, DESCRIPTION_CHAR_THRESHOLD - 1),
])
async def test_maybe_generate_skips(broadcast, existing_description, chars):
    make_session(sid="s1")
    if existing_description:
        save_description("s1", existing_description)
    make_message("s1", "user", "x" * chars)

    with patch("hypergolic.sessions.description.generate.asyncio.create_task") as mock_create_task:
        await maybe_generate_description("s1", broadcast)
        mock_create_task.assert_not_called()


async def test_maybe_generate_fires_at_threshold(broadcast):
    make_session(sid="s1")
    make_message("s1", "user", "x" * DESCRIPTION_CHAR_THRESHOLD)

    sentinel = object()
    with patch(
        "hypergolic.sessions.description.generate._generate_description",
        new=MagicMock(return_value=sentinel),
    ):
        with patch("hypergolic.sessions.description.generate.asyncio.create_task") as mock_create_task:
            await maybe_generate_description("s1", broadcast)
            mock_create_task.assert_called_once_with(sentinel)


def test_get_dispatch_prompt():
    make_session(sid="parent")
    raw = (
        "Research the architecture of the project"
        "\n\nCRITICAL: You MUST call `conclude` as your final action"
        " \u2014 the parent session is deadlocked until you do. "
        "Never end your turn without calling conclude."
    )
    make_session(sid="child", parent_id="parent", dispatch_prompt=raw)
    make_session(sid="child2", parent_id="parent", dispatch_prompt="Do the thing")

    assert _get_dispatch_prompt("parent") is None
    assert _get_dispatch_prompt("child") == "Research the architecture of the project"
    assert _get_dispatch_prompt("child2") == "Do the thing"


async def test_maybe_generate_fires_immediately_for_child_session(broadcast):
    make_session(sid="parent")
    make_session(sid="child", parent_id="parent", dispatch_prompt="Investigate the bug in module X")

    sentinel = object()
    with patch(
        "hypergolic.sessions.description.generate._generate_description",
        new=MagicMock(return_value=sentinel),
    ):
        with patch("hypergolic.sessions.description.generate.asyncio.create_task") as mock_create_task:
            await maybe_generate_description("child", broadcast)
            mock_create_task.assert_called_once_with(sentinel)


async def test_generate_description_uses_dispatch_prompt_for_child(broadcast):
    make_session(sid="parent")
    make_session(sid="child", parent_id="parent", dispatch_prompt="Analyze the database schema")

    mock_generate = AsyncMock(return_value="Database schema analysis")
    with patch("hypergolic.sessions.description.generate.generate_text", new=mock_generate):
        await _generate_description("child", broadcast)

    assert get_session_description("child") == "Database schema analysis"
    call_kwargs = mock_generate.call_args[1]
    assert "Analyze the database schema" in call_kwargs["messages"][0]["content"]
    assert "<session_messages>" in call_kwargs["messages"][0]["content"]
