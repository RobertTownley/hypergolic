"""Tests for tools/truncation.py."""

from typing import Any, cast

import pytest

from hypergolic.harness.primitives.results import ToolResult
from hypergolic.tools.truncation import result_block, truncate_tool_output
from tests.helpers.blocks import all_texts


# ── result_block ───────────────────────────────────────────────────


@pytest.mark.parametrize("is_error", [False, True])
def test_result_block(is_error):
    output = ToolResult(content=[{"type": "text", "text": "ok"}], is_error=is_error)
    block = result_block("tu-1", output)
    assert block["tool_use_id"] == "tu-1"
    assert block["type"] == "tool_result"
    assert block["content"] == output.content
    assert block["is_error"] is is_error


def test_result_block_carries_meta_for_the_ui():
    output = ToolResult(content=[{"type": "text", "text": "ok"}], meta={"k": "v"})
    block = result_block("tu-1", output)
    assert cast(dict[str, Any], block)["meta"] == {"k": "v"}


def test_result_block_omits_meta_when_unset():
    assert "meta" not in result_block("tu-1", ToolResult.text("ok"))


# ── truncate_tool_output ────────────────────────────────────────────


def test_truncate_preserves_meta():
    output = ToolResult(content=[{"type": "text", "text": "x" * 100}], meta={"k": "v"})
    assert truncate_tool_output(output, limit=10).meta == {"k": "v"}


def test_truncate_under_limit():
    output = ToolResult(content=[{"type": "text", "text": "short"}])
    result = truncate_tool_output(output, limit=1000)
    assert result is output  # returned unchanged


def test_truncate_over_limit_single_block():
    output = ToolResult(content=[{"type": "text", "text": "a" * 100}])
    result = truncate_tool_output(output, limit=50)
    texts = all_texts(result.content)
    assert len(texts[0]) == 50
    assert "truncated" in texts[-1].lower()


def test_truncate_over_limit_multiple_blocks():
    output = ToolResult(content=[
        {"type": "text", "text": "a" * 30},
        {"type": "text", "text": "b" * 30},
    ])
    result = truncate_tool_output(output, limit=40)
    texts = all_texts(result.content)
    assert texts[0] == "a" * 30
    assert texts[1] == "b" * 10
    assert "truncated" in texts[-1].lower()


def test_truncate_preserves_non_text_blocks():
    content: list[Any] = [
        {"type": "image", "data": "img"},
        {"type": "text", "text": "x" * 100},
    ]
    output = ToolResult(content=content)
    result = truncate_tool_output(output, limit=10)
    assert result.content[0] == {"type": "image", "data": "img"}


def test_truncate_preserves_is_error():
    output = ToolResult(content=[{"type": "text", "text": "x" * 100}], is_error=True)
    result = truncate_tool_output(output, limit=10)
    assert result.is_error is True


def test_truncate_with_zero_remaining_skips_later_blocks():
    """When remaining reaches 0, later text blocks are dropped entirely."""
    output = ToolResult(content=[
        {"type": "text", "text": "a" * 50},
        {"type": "text", "text": "b" * 50},
    ])
    result = truncate_tool_output(output, limit=50)
    texts = all_texts(result.content)
    assert texts == ["a" * 50, texts[-1]]
    assert "truncated" in texts[-1].lower()
