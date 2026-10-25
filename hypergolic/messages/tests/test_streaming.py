"""Tests for hypergolic.messages.streaming."""

from unittest.mock import MagicMock

from anthropic.lib.streaming._types import ParsedContentBlockStopEvent
from anthropic.types import (
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
)

from hypergolic.messages.streaming import handle_streaming_event
from hypergolic.messages.types import BroadcastEvent


def _make_text_block_start(index: int = 0) -> RawContentBlockStartEvent:
    event = MagicMock(spec=RawContentBlockStartEvent)
    event.index = index
    event.content_block = MagicMock()
    event.content_block.type = "text"
    return event


def _make_tool_use_block_start(
    index: int = 0,
    tool_id: str = "tu-1",
    tool_name: str = "my_tool",
) -> RawContentBlockStartEvent:
    event = MagicMock(spec=RawContentBlockStartEvent)
    event.index = index
    event.content_block = MagicMock()
    event.content_block.type = "tool_use"
    event.content_block.name = tool_name
    event.content_block.id = tool_id
    return event


def _make_text_delta(index: int = 0, text: str = "hello") -> RawContentBlockDeltaEvent:
    event = MagicMock(spec=RawContentBlockDeltaEvent)
    event.index = index
    event.delta = MagicMock()
    event.delta.type = "text_delta"
    event.delta.text = text
    return event


def _make_input_json_delta(
    index: int = 0, partial_json: str = '{"key":'
) -> RawContentBlockDeltaEvent:
    event = MagicMock(spec=RawContentBlockDeltaEvent)
    event.index = index
    event.delta = MagicMock()
    event.delta.type = "input_json_delta"
    event.delta.partial_json = partial_json
    return event


def _make_block_stop(index: int = 0) -> ParsedContentBlockStopEvent:
    event = MagicMock(spec=ParsedContentBlockStopEvent)
    event.index = index
    return event


async def test_text_block_start_broadcasts_correct_event(broadcast):
    event = _make_text_block_start(index=0)

    await handle_streaming_event(event, broadcast, session_id="sess-1")

    broadcast.assert_awaited_once()
    evt: BroadcastEvent = broadcast.call_args[0][0]
    assert evt.type == "content_block_start"
    assert evt.role == "assistant"
    assert evt.session_id == "sess-1"
    block = evt.content[0]
    assert block["type"] == "text"
    assert block["index"] == 0
    assert block["text"] == ""


async def test_tool_use_block_start_broadcasts_correct_event(broadcast):
    event = _make_tool_use_block_start(index=1, tool_id="tu-42", tool_name="cat")

    await handle_streaming_event(event, broadcast, session_id="sess-2")

    broadcast.assert_awaited_once()
    evt: BroadcastEvent = broadcast.call_args[0][0]
    assert evt.type == "content_block_start"
    block = evt.content[0]
    assert block["type"] == "tool_call"
    assert block["id"] == "tu-42"
    assert block["name"] == "cat"
    assert block["display_name"] == "cat"  # no mapping provided
    assert block["input"] == {}
    assert block["index"] == 1


async def test_tool_use_block_start_uses_display_name_mapping(broadcast):
    event = _make_tool_use_block_start(tool_name="cat")
    display_names = {"cat": "Read Files"}

    await handle_streaming_event(
        event, broadcast, session_id="sess-3", tool_display_names=display_names
    )

    evt: BroadcastEvent = broadcast.call_args[0][0]
    block = evt.content[0]
    assert block["display_name"] == "Read Files"


async def test_tool_use_block_start_unmapped_tool_uses_name_as_display(broadcast):
    event = _make_tool_use_block_start(tool_name="unknown_tool")
    display_names = {"other_tool": "Other Tool"}

    await handle_streaming_event(
        event, broadcast, session_id="sess-4", tool_display_names=display_names
    )

    evt: BroadcastEvent = broadcast.call_args[0][0]
    block = evt.content[0]
    assert block["display_name"] == "unknown_tool"


async def test_text_delta_broadcasts_correct_event(broadcast):
    event = _make_text_delta(index=0, text="world")

    await handle_streaming_event(event, broadcast, session_id="sess-5")

    broadcast.assert_awaited_once()
    evt: BroadcastEvent = broadcast.call_args[0][0]
    assert evt.type == "content_block_delta"
    assert evt.role == "assistant"
    assert evt.session_id == "sess-5"
    delta = evt.content[0]
    assert delta["type"] == "text_delta"
    assert delta["text"] == "world"
    assert delta["index"] == 0


async def test_input_json_delta_broadcasts_correct_event(broadcast):
    event = _make_input_json_delta(index=2, partial_json='{"key": "val')

    await handle_streaming_event(event, broadcast, session_id="sess-6")

    broadcast.assert_awaited_once()
    evt: BroadcastEvent = broadcast.call_args[0][0]
    assert evt.type == "content_block_delta"
    delta = evt.content[0]
    assert delta["type"] == "input_json_delta"
    assert delta["partial_json"] == '{"key": "val'
    assert delta["index"] == 2


async def test_block_stop_broadcasts_correct_event(broadcast):
    event = _make_block_stop(index=3)

    await handle_streaming_event(event, broadcast, session_id="sess-7")

    broadcast.assert_awaited_once()
    evt: BroadcastEvent = broadcast.call_args[0][0]
    assert evt.type == "content_block_stop"
    assert evt.role == "assistant"
    assert evt.session_id == "sess-7"
    assert evt.content == [{"index": 3}]


async def test_unrecognised_event_type_does_not_broadcast(broadcast):
    unknown_event = MagicMock()  # no spec — not an instance of any known type

    await handle_streaming_event(unknown_event, broadcast, session_id="sess-8")

    broadcast.assert_not_awaited()


def _make_thinking_block_start(index: int = 0) -> RawContentBlockStartEvent:
    event = MagicMock(spec=RawContentBlockStartEvent)
    event.index = index
    event.content_block = MagicMock()
    event.content_block.type = "thinking"
    return event


def _make_thinking_delta(
    index: int = 0, thinking: str = "hmm"
) -> RawContentBlockDeltaEvent:
    event = MagicMock(spec=RawContentBlockDeltaEvent)
    event.index = index
    event.delta = MagicMock()
    event.delta.type = "thinking_delta"
    event.delta.thinking = thinking
    return event


async def test_thinking_block_start_broadcasts_empty_thinking(broadcast):
    event = _make_thinking_block_start(index=0)

    await handle_streaming_event(event, broadcast, session_id="sess-t1")

    broadcast.assert_awaited_once()
    evt: BroadcastEvent = broadcast.call_args[0][0]
    assert evt.type == "content_block_start"
    block = evt.content[0]
    assert block["type"] == "thinking"
    assert block["thinking"] == ""


async def test_thinking_delta_broadcasts_thinking_text(broadcast):
    event = _make_thinking_delta(index=0, thinking="step 1: ")

    await handle_streaming_event(event, broadcast, session_id="sess-t2")

    broadcast.assert_awaited_once()
    evt: BroadcastEvent = broadcast.call_args[0][0]
    assert evt.type == "content_block_delta"
    delta = evt.content[0]
    assert delta["type"] == "thinking_delta"
    assert delta["thinking"] == "step 1: "


async def test_signature_delta_is_not_broadcast(broadcast):
    event = MagicMock(spec=RawContentBlockDeltaEvent)
    event.index = 0
    event.delta = MagicMock()
    event.delta.type = "signature_delta"
    event.delta.signature = "opaque=="

    await handle_streaming_event(event, broadcast, session_id="sess-t3")

    broadcast.assert_not_awaited()
