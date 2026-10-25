from typing import Any, cast

import pytest
from pydantic import BaseModel

from hypergolic.messages.types import BroadcastEvent
from hypergolic.websocket.helpers import build_content_blocks, serialize_event
from hypergolic.websocket.schemas import ConnectMessage


class _Foo(BaseModel):
    x: int = 1


# ── serialize_event ─────────────────────────────────────────────────


def test_serialize_event_basic():
    event = BroadcastEvent(type="test", role="user", content=[{"key": "val"}])
    result = serialize_event(event)
    assert result["type"] == "test"
    assert result["role"] == "user"
    assert result["content"] == [{"key": "val"}]
    assert "session_id" not in result
    assert "model" not in result


def test_serialize_event_with_optional_fields():
    event = BroadcastEvent(
        type="t",
        role="assistant",
        content=[],
        session_id="s-1",
        model="claude",
        stop_reason="end_turn",
        message_id="m-1",
        usage={"input": 10, "output": 20},
    )
    result = serialize_event(event)
    assert result["session_id"] == "s-1"
    assert result["model"] == "claude"
    assert result["stop_reason"] == "end_turn"
    assert result["message_id"] == "m-1"
    assert result["usage"] == {"input": 10, "output": 20}


@pytest.mark.parametrize(
    "content, expected",
    [
        ([_Foo()], [{"x": 1}]),  # pydantic models are dumped to dicts
        ([42], ["42"]),          # anything else is stringified
    ],
)
def test_serialize_event_content_normalization(content, expected):
    result = serialize_event(BroadcastEvent(type="t", role="r", content=content))
    assert result["content"] == expected


# ── build_content_blocks ────────────────────────────────────────────


def test_build_content_blocks_text_only():
    blocks = build_content_blocks(ConnectMessage(message="hello"))
    assert len(blocks) == 1
    assert blocks[0]["type"] == "text"
    assert cast(dict[str, Any], blocks[0])["text"] == "hello"


@pytest.mark.parametrize(
    "extra_block",
    [
        {"type": "text", "text": "preamble"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "abc"},
        },
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": "abc"},
        },
    ],
)
def test_build_content_blocks_prepends_extra_blocks(extra_block):
    req = ConnectMessage(message="hello", content_blocks=[extra_block])
    blocks = build_content_blocks(req)
    assert len(blocks) == 2
    assert dict(blocks[0]) == extra_block
    assert cast(dict[str, Any], blocks[1])["text"] == "hello"


# ── format_error_detail ─────────────────────────────────────────────
