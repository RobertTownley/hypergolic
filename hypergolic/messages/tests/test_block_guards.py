"""Tests for hypergolic.messages.block_guards."""

from hypergolic.messages.block_guards import (
    is_text_block,
    is_tool_result_block,
    is_tool_use_block,
    iter_content_blocks,
)


def test_is_text_block_true():
    assert is_text_block({"type": "text", "text": "hi"}) is True


def test_is_text_block_wrong_type():
    assert is_text_block({"type": "image"}) is False


def test_is_text_block_non_dict():
    assert is_text_block("not a dict") is False


def test_is_tool_use_block_true():
    assert is_tool_use_block({"type": "tool_use", "id": "x"}) is True


def test_is_tool_use_block_false():
    assert is_tool_use_block({"type": "text"}) is False


def test_is_tool_use_block_non_dict():
    assert is_tool_use_block(None) is False


def test_is_tool_result_block_true():
    assert is_tool_result_block({"type": "tool_result", "tool_use_id": "x"}) is True


def test_is_tool_result_block_false():
    assert is_tool_result_block({"type": "text"}) is False


def test_is_tool_result_block_non_dict():
    assert is_tool_result_block(42) is False


def test_iter_content_blocks_none():
    assert iter_content_blocks(None) == []


def test_iter_content_blocks_string():
    assert iter_content_blocks("hello") == [{"type": "text", "text": "hello"}]


def test_iter_content_blocks_list_of_dicts():
    blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert iter_content_blocks(blocks) == blocks


def test_iter_content_blocks_filters_non_dicts():
    blocks = [{"type": "text", "text": "a"}, "not-a-dict", 42]
    assert iter_content_blocks(blocks) == [{"type": "text", "text": "a"}]
