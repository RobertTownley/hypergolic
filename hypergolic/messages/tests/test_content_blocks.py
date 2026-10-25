"""Tests for hypergolic.messages.content_blocks."""

import json
from unittest.mock import MagicMock

import pytest

from hypergolic.messages.content_blocks import (
    serialize_anthropic_content_block,
    serialize_content_blocks,
    serialize_image_block,
    serialize_text_block,
    serialize_tool_call_block,
    serialize_tool_result_block,
)


def test_serialize_text_block():
    assert serialize_text_block("hello world") == {"type": "text", "text": "hello world"}
    assert serialize_text_block("") == {"type": "text", "text": ""}


def test_serialize_image_block():
    assert serialize_image_block(media_type="image/png", data="base64data") == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "base64data"},
    }


def test_serialize_tool_call_block():
    result = serialize_tool_call_block(id="tu-1", name="cat", input={"paths": ["a.py"]})
    assert result == {
        "type": "tool_call",
        "id": "tu-1",
        "name": "cat",
        "display_name": "cat",  # falls back to name
        "input": {"paths": ["a.py"]},
    }

    explicit = serialize_tool_call_block(
        id="tu-2", name="cat", input={}, display_name="Read Files"
    )
    assert explicit["display_name"] == "Read Files"


def test_serialize_tool_result_block():
    content = [{"type": "text", "text": "result text"}]
    result = serialize_tool_result_block(tool_use_id="tu-1", content=content)
    assert result == {
        "type": "tool_result",
        "tool_use_id": "tu-1",
        "content": content,
        "is_error": False,
    }
    assert serialize_tool_result_block(tool_use_id="tu-2", content=[], is_error=True)[
        "is_error"
    ] is True


def test_serialize_tool_result_block_carries_meta_to_the_ui():
    raw = {
        "type": "tool_result",
        "tool_use_id": "tu-1",
        "content": [{"type": "text", "text": "ok"}],
        "meta": {"workflow_state_name": "Draft"},
    }
    assert serialize_anthropic_content_block(raw)["meta"] == {"workflow_state_name": "Draft"}


@pytest.mark.parametrize("block, expected", [
    # text dict passes through
    ({"type": "text", "text": "hello"}, {"type": "text", "text": "hello"}),
    # tool_use becomes tool_call; name doubles as display_name without mapping
    (
        {"type": "tool_use", "id": "tu-1", "name": "cat", "input": {"paths": ["x.py"]}},
        {"type": "tool_call", "id": "tu-1", "name": "cat",
         "display_name": "cat", "input": {"paths": ["x.py"]}},
    ),
    # tool_use string input: valid JSON is parsed, garbage becomes {}
    (
        {"type": "tool_use", "id": "tu-3", "name": "tool",
         "input": json.dumps({"key": "value"})},
        {"type": "tool_call", "id": "tu-3", "name": "tool",
         "display_name": "tool", "input": {"key": "value"}},
    ),
    (
        {"type": "tool_use", "id": "tu-4", "name": "tool", "input": "not json at all"},
        {"type": "tool_call", "id": "tu-4", "name": "tool",
         "display_name": "tool", "input": {}},
    ),
    # image passes through
    (
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/jpeg", "data": "abc123"}},
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/jpeg", "data": "abc123"}},
    ),
    # tool_result: list content passes through, string content is wrapped
    (
        {"type": "tool_result", "tool_use_id": "tu-1",
         "content": [{"type": "text", "text": "result"}], "is_error": False},
        {"type": "tool_result", "tool_use_id": "tu-1",
         "content": [{"type": "text", "text": "result"}], "is_error": False},
    ),
    (
        {"type": "tool_result", "tool_use_id": "tu-3",
         "content": "error message", "is_error": True},
        {"type": "tool_result", "tool_use_id": "tu-3",
         "content": [{"type": "text", "text": "error message"}], "is_error": True},
    ),
    # unknown block type is returned as-is
    (
        {"type": "unknown_custom", "data": "something"},
        {"type": "unknown_custom", "data": "something"},
    ),
    # non-dict, non-model fallbacks stringify to text blocks
    ("just a string", {"type": "text", "text": "just a string"}),
    (42, {"type": "text", "text": "42"}),
])
def test_serialize_anthropic_content_block(block, expected):
    assert serialize_anthropic_content_block(block) == expected


def test_serialize_anthropic_content_block_model_dump():
    mock_block = MagicMock()
    mock_block.model_dump.return_value = {"type": "text", "text": "from model"}
    assert serialize_anthropic_content_block(mock_block) == {"type": "text", "text": "from model"}
    mock_block.model_dump.assert_called_once_with(mode="json")


def test_serialize_anthropic_content_block_tool_use_display_name_mapping():
    block = {"type": "tool_use", "id": "tu-2", "name": "write", "input": {}}
    result = serialize_anthropic_content_block(
        block, tool_display_names={"write": "Write Files"}
    )
    assert result["display_name"] == "Write Files"


def test_serialize_content_blocks():
    # A bare string becomes a single text block.
    assert serialize_content_blocks("hello") == [{"type": "text", "text": "hello"}]
    assert serialize_content_blocks([]) == []

    blocks = [
        {"type": "text", "text": "a"},
        {"type": "tool_use", "id": "tu-1", "name": "cat", "input": {}},
    ]
    result = serialize_content_blocks(blocks, tool_display_names={"cat": "Read Files"})
    assert result[0] == {"type": "text", "text": "a"}
    assert result[1]["display_name"] == "Read Files"
