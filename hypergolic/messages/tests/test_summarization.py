"""Tests for hypergolic.messages.summarization."""

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from anthropic import BadRequestError
from anthropic.types import Message, MessageParam, TextBlock

from hypergolic.enums import ModelTier
from hypergolic.messages.summarization import (
    SUMMARY_MAX_TOKENS,
    TOOL_INPUT_MAX_CHARS,
    TOOL_RESULT_MAX_CHARS,
    _build_system_prompt,
    _truncate_tool_result,
    build_conversation_transcript,
    call_summarization_model,
    extract_summary_text,
)
from tests._factories import build_assistant_message


def _msgs(*messages: Any) -> list[MessageParam]:
    return cast(list[MessageParam], list(messages))


def _make_response(content_blocks) -> Message:
    return build_assistant_message(content=content_blocks)


def _bad_request(message: str) -> BadRequestError:
    return BadRequestError(
        message,
        response=httpx2.Response(400, request=httpx2.Request("POST", "http://x")),
        body=None,
    )


def test_truncate_tool_result():
    assert _truncate_tool_result("short text") == "short text"
    at_limit = "x" * TOOL_RESULT_MAX_CHARS
    assert _truncate_tool_result(at_limit) == at_limit  # no truncation at the limit

    over = _truncate_tool_result("x" * (TOOL_RESULT_MAX_CHARS + 100))
    assert over.startswith("x" * TOOL_RESULT_MAX_CHARS)
    assert "truncated" in over

    custom = _truncate_tool_result("hello world", max_chars=5)
    assert custom.startswith("hello")
    assert "truncated" in custom


@pytest.mark.parametrize("message, expected_text", [
    ({"role": "user", "content": [{"type": "text", "text": "hello there"}]},
     "[user]: hello there"),
    ({"role": "assistant", "content": [{"type": "text", "text": "hi back"}]},
     "[assistant]: hi back"),
    ({"role": "user", "content": "plain string content"},
     "[user]: plain string content"),
    ({"role": "assistant",
      "content": [{"type": "tool_use", "name": "cat", "input": {"paths": ["a.py"]}}]},
     "[Tool call: cat"),
    ({"role": "user",
      "content": [{"type": "tool_result", "tool_use_id": "tu-1",
                   "content": "the result text", "is_error": False}]},
     "[Tool result: the result text]"),
    ({"role": "user",
      "content": [{"type": "tool_result", "tool_use_id": "tu-1",
                   "content": [{"type": "text", "text": "list result"}], "is_error": False}]},
     "[Tool result: list result]"),
    ({"role": "user",
      "content": [{"type": "tool_result", "tool_use_id": "tu-1",
                   "content": "something broke", "is_error": True}]},
     "[Tool error: something broke]"),
])
def test_build_conversation_transcript_renders_blocks(message, expected_text):
    result = build_conversation_transcript(_msgs(message))
    assert len(result) == 1
    assert expected_text in result[0]["text"]


@pytest.mark.parametrize("message", [
    {"role": "user", "content": [{"type": "text", "text": "   "}]},  # whitespace block
    {"role": "user", "content": []},
    {"role": "user", "content": "   "},  # whitespace string content
    {"role": "user", "content": ["not a dict"]},  # non-dict block
])
def test_build_conversation_transcript_skips_empty(message):
    assert build_conversation_transcript(_msgs(message)) == []


def test_build_conversation_transcript_multiple_messages():
    messages = _msgs(
        {"role": "user", "content": [{"type": "text", "text": "question"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "answer"}]},
    )
    result = build_conversation_transcript(messages)
    assert len(result) == 2
    assert "[user]:" in result[0]["text"]
    assert "[assistant]:" in result[1]["text"]


def test_build_conversation_transcript_tool_result_long_string_truncated():
    long_text = "x" * (TOOL_RESULT_MAX_CHARS + 100)
    messages = _msgs(
        {"role": "user",
         "content": [{"type": "tool_result", "tool_use_id": "tu-1",
                      "content": long_text, "is_error": False}]},
    )
    result = build_conversation_transcript(messages)
    assert "truncated" in result[0]["text"]


def test_build_system_prompt_includes_file_when_exists():
    prompt_text = "You are a summarization assistant."
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = prompt_text
    result = _build_system_prompt(mock_path)

    assert len(result) == 1
    assert result[0]["type"] == "text"
    assert result[0]["text"] == prompt_text


def test_build_system_prompt_empty_when_file_missing():
    mock_path = MagicMock()
    mock_path.exists.return_value = False
    result = _build_system_prompt(mock_path)

    assert result == []


def test_extract_summary_text():
    response = _make_response([
        TextBlock(type="text", text="Part one. "),
        TextBlock(type="text", text="Part two."),
    ])
    assert extract_summary_text(response) == "Part one. Part two."

    non_text = MagicMock()
    non_text.type = "tool_use"
    mock_response = MagicMock()
    mock_response.content = [non_text, TextBlock(type="text", text="summary here")]
    assert extract_summary_text(mock_response) == "summary here"


@pytest.mark.parametrize("blocks", [[], [TextBlock(type="text", text="   ")]])
def test_extract_summary_text_raises_on_empty(blocks):
    with pytest.raises(ValueError, match="empty response"):
        extract_summary_text(_make_response(blocks))


def test_build_conversation_transcript_tool_input_truncated():
    messages = _msgs({
        "role": "assistant",
        "content": [{
            "type": "tool_use",
            "name": "cmd",
            "input": {"command": "x" * (TOOL_INPUT_MAX_CHARS + 500)},
        }],
    })
    text = build_conversation_transcript(messages)[0]["text"]
    assert "truncated" in text
    assert len(text) < TOOL_INPUT_MAX_CHARS + 200


def test_extract_summary_text_error_reports_response_shape():
    thinking = MagicMock()
    thinking.type = "thinking"
    response = MagicMock()
    response.content = [thinking]
    response.model = "claude-opus-5"
    response.stop_reason = "max_tokens"
    response.usage.output_tokens = 1024

    with pytest.raises(ValueError) as exc_info:
        extract_summary_text(response)

    message = str(exc_info.value)
    assert "max_tokens" in message
    assert "thinking" in message
    assert "claude-opus-5" in message


def test_extract_summary_text_error_without_usage():
    response = MagicMock()
    response.content = []
    response.model = "m"
    response.stop_reason = "end_turn"
    response.usage = None

    with pytest.raises(ValueError, match="output_tokens=None"):
        extract_summary_text(response)


def _summarizable() -> list[MessageParam]:
    return _msgs({"role": "user", "content": [{"type": "text", "text": "hello"}]})


async def test_call_summarization_model_leaves_thinking_at_provider_default():
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_make_response([TextBlock(type="text", text="a summary")])
    )
    with patch(
        "hypergolic.messages.summarization.client_for_tier", return_value=client
    ) as for_tier:
        response = await call_summarization_model(ModelTier.HIGH, _summarizable())

    for_tier.assert_called_once_with(ModelTier.HIGH)
    assert extract_summary_text(response) == "a summary"
    call = client.messages.create.await_args
    assert call is not None
    assert "thinking" not in call.kwargs
    assert call.kwargs["max_tokens"] == SUMMARY_MAX_TOKENS


async def test_call_summarization_model_propagates_provider_error():
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=_bad_request("context too long"))
    with (
        patch("hypergolic.messages.summarization.client_for_tier", return_value=client),
        pytest.raises(BadRequestError, match="context too long"),
    ):
        await call_summarization_model(ModelTier.HIGH, _summarizable())

    assert client.messages.create.await_count == 1


async def test_call_summarization_model_rejects_empty_transcript():
    with (
        patch("hypergolic.messages.summarization.client_for_tier", return_value=MagicMock()),
        pytest.raises(ValueError, match="No message content"),
    ):
        await call_summarization_model(ModelTier.HIGH, _msgs())
