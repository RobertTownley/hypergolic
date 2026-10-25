"""Tests for hypergolic.harness.primitives.ToolResult helpers."""

import pytest

from hypergolic.harness.primitives.results import ToolResult


def test_text_constructor_builds_single_text_block():
    output = ToolResult.text("hello")
    assert output.content == [{"type": "text", "text": "hello"}]
    assert output.is_error is False


def test_text_constructor_with_flags():
    output = ToolResult.text("boom", is_error=True)
    assert output.is_error is True


def test_append_text_returns_new_instance_with_block_appended():
    original = ToolResult.text("first")
    appended = original.append_text("second")

    assert appended is not original
    assert appended.content == [
        {"type": "text", "text": "first"},
        {"type": "text", "text": "second"},
    ]
    assert original.content == [{"type": "text", "text": "first"}]


def test_append_text_preserves_flags():
    original = ToolResult.text("x", is_error=True)
    appended = original.append_text("y")
    assert appended.is_error is True


def test_iter_text_blocks_yields_only_text_blocks():
    output = ToolResult(content=[
        {"type": "text", "text": "a"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "xxx"}},
        {"type": "text", "text": "b"},
    ])
    blocks = list(output.iter_text_blocks())
    assert len(blocks) == 2
    assert [b["text"] for b in blocks] == ["a", "b"]


def test_iter_text_blocks_empty_content():
    output = ToolResult()
    assert list(output.iter_text_blocks()) == []


def test_total_text_chars_sums_across_text_blocks():
    output = ToolResult(content=[
        {"type": "text", "text": "hello"},
        {"type": "text", "text": "world!"},
    ])
    assert output.total_text_chars() == len("hello") + len("world!")


def test_total_text_chars_ignores_non_text_blocks():
    output = ToolResult(content=[
        {"type": "text", "text": "abc"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "xxx"}},
    ])
    assert output.total_text_chars() == 3


def test_total_text_chars_empty():
    assert ToolResult().total_text_chars() == 0


def test_first_text():
    assert ToolResult.text("hello").first_text() == "hello"

    with pytest.raises(IndexError, match="no content blocks"):
        ToolResult().first_text()

    image = ToolResult(content=[
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}},
    ])
    with pytest.raises(TypeError, match="Expected text block, got 'image'"):
        image.first_text()
