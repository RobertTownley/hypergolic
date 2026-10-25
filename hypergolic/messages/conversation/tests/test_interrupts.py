from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import TextBlock, ToolUseBlock

from hypergolic.messages.conversation.interrupts import (
    _build_interrupt_tool_results,
    _extract_partial_text,
    _persist_partial_assistant_message,
    persist_interrupt_tool_results,
)
from hypergolic.messages.types import INTERRUPTED_SUFFIX
from hypergolic.messages import message_rows
from tests._factories import build_assistant_message
from tests.conftest import make_project, make_session


def test_extract_partial_text_with_text_block():
    stream = MagicMock()
    snapshot = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = "partial response"
    snapshot.content = [block]
    stream.current_message_snapshot = snapshot

    result = _extract_partial_text(stream)
    assert result == "partial response"


def test_extract_partial_text_multiple_text_blocks():
    stream = MagicMock()
    snapshot = MagicMock()
    block1 = MagicMock()
    block1.type = "text"
    block1.text = "first"
    block2 = MagicMock()
    block2.type = "text"
    block2.text = "second"
    snapshot.content = [block1, block2]
    stream.current_message_snapshot = snapshot

    result = _extract_partial_text(stream)
    assert result == "first\n\nsecond"


def test_extract_partial_text_no_text_blocks():
    stream = MagicMock()
    snapshot = MagicMock()
    block = MagicMock()
    block.type = "tool_use"
    block.text = None
    snapshot.content = [block]
    stream.current_message_snapshot = snapshot

    result = _extract_partial_text(stream)
    assert result is None


def test_extract_partial_text_empty_snapshot():
    stream = MagicMock()
    snapshot = MagicMock()
    snapshot.content = []
    stream.current_message_snapshot = snapshot

    result = _extract_partial_text(stream)
    assert result is None


def test_extract_partial_text_none_snapshot():
    stream = MagicMock()
    stream.current_message_snapshot = None

    result = _extract_partial_text(stream)
    assert result is None


def test_extract_partial_text_stream_raises_exception():
    stream = MagicMock()
    type(stream).current_message_snapshot = property(lambda self: (_ for _ in ()).throw(RuntimeError("stream error")))

    result = _extract_partial_text(stream)
    assert result is None


async def test_persist_partial_assistant_message_creates_db_entry():
    make_project()
    session_id = make_session()

    await _persist_partial_assistant_message(session_id, "partial text")

    [msg] = message_rows.for_session(session_id)
    assert msg.role == "assistant"
    assert msg.stop_reason == "interrupted"
    assert len(msg.content) == 1
    assert msg.content[0]["type"] == "text"
    assert INTERRUPTED_SUFFIX in msg.content[0]["text"]
    assert "partial text" in msg.content[0]["text"]


def test_build_interrupt_tool_results_with_tool_use_blocks():
    response = build_assistant_message(
        content=[
            TextBlock(type="text", text="thinking..."),
            ToolUseBlock(type="tool_use", id="tu-1", name="cat", input={"paths": ["a.py"]}),
            ToolUseBlock(type="tool_use", id="tu-2", name="write", input={"files": []}),
        ]
    )

    result = _build_interrupt_tool_results(response)
    assert result is not None
    assert result["role"] == "user"
    content = cast(list[dict[str, Any]], result["content"])
    assert len(content) == 2
    assert content[0]["type"] == "tool_result"
    assert content[0]["tool_use_id"] == "tu-1"
    assert content[0]["is_error"] is True
    assert content[1]["tool_use_id"] == "tu-2"


def test_build_interrupt_tool_results_without_tool_use_blocks():
    response = build_assistant_message(
        content=[TextBlock(type="text", text="just text")]
    )

    result = _build_interrupt_tool_results(response)
    assert result is None


def test_build_interrupt_tool_results_tool_result_content():
    response = build_assistant_message(
        content=[
            ToolUseBlock(type="tool_use", id="tu-abc", name="my_tool", input={}),
        ]
    )

    result = _build_interrupt_tool_results(response)
    assert result is not None
    content = cast(list[dict[str, Any]], result["content"])
    inner = cast(list[dict[str, Any]], content[0]["content"])
    assert inner[0]["text"] == "Interrupted by user"


async def test_persist_interrupt_tool_results_calls_persist_when_tool_blocks():
    make_project()
    session_id = make_session()

    response = build_assistant_message(
        content=[
            ToolUseBlock(type="tool_use", id="tu-1", name="cat", input={}),
        ]
    )

    with patch(
        "hypergolic.messages.conversation.interrupts.persist_messages",
        new=AsyncMock(),
    ) as mock_persist:
        await persist_interrupt_tool_results(session_id, response)

    mock_persist.assert_awaited_once()
    call_kwargs = mock_persist.call_args[1]
    assert call_kwargs["session_id"] == session_id


async def test_persist_interrupt_tool_results_no_call_when_no_tool_blocks():
    make_project()
    session_id = make_session()

    response = build_assistant_message(
        content=[TextBlock(type="text", text="no tools here")]
    )

    with patch(
        "hypergolic.messages.conversation.interrupts.persist_messages",
        new=AsyncMock(),
    ) as mock_persist:
        await persist_interrupt_tool_results(session_id, response)

    mock_persist.assert_not_awaited()
