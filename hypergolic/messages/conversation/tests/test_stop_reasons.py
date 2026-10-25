"""Tests for hypergolic.messages.conversation.stop_reasons."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import TextBlock, ToolUseBlock

from hypergolic.messages.block_guards import is_text_block
from hypergolic.messages.conversation.stop_reasons import (
    CONTINUE_MESSAGES,
    TRUNCATED_TOOL_USE_ERROR,
    _build_truncated_tool_results,
    handle_continue,
)
from hypergolic.messages.types import BroadcastEvent, UserInterrupt
from tests._factories import build_assistant_message, build_session


async def _run_handle_continue(
    reason: str, broadcast, *, response=None, check_cancelled=None
) -> AsyncMock:
    """Invoke handle_continue with persist_messages mocked; return the mock."""
    session = build_session(sid="sess-1", project_path="/tmp/test")
    with patch(
        "hypergolic.messages.conversation.stop_reasons.persist_messages",
        new=AsyncMock(),
    ) as mock_persist:
        await handle_continue(
            reason, session, broadcast, check_cancelled or MagicMock(),
            response=response,
        )
    return mock_persist


def _persisted(mock_persist: AsyncMock) -> dict[str, Any]:
    return mock_persist.call_args[1]["messages"][0]


@pytest.mark.parametrize("reason", ["max_tokens", "pause_turn"])
def test_continue_messages_has_reason(reason):
    assert reason in CONTINUE_MESSAGES
    assert reason in CONTINUE_MESSAGES[reason]


def test_build_truncated_tool_results_no_tool_use():
    response = build_assistant_message("max_tokens")
    assert _build_truncated_tool_results(response) == []


def test_build_truncated_tool_results_with_tool_use():
    response = build_assistant_message(
        "max_tokens",
        content=[
            TextBlock(type="text", text="Let me do that"),
            ToolUseBlock(type="tool_use", id="tu-1", name="cat", input={"paths": ["a.py"]}),
            ToolUseBlock(type="tool_use", id="tu-2", name="write", input={"files": []}),
        ],
    )
    results = _build_truncated_tool_results(response)
    assert len(results) == 2
    assert results[0]["type"] == "tool_result"
    assert results[0]["tool_use_id"] == "tu-1"
    assert results[0]["is_error"] is True
    first = list(results[0]["content"])[0]  # type: ignore[arg-type]
    assert is_text_block(first)
    assert first["text"] == TRUNCATED_TOOL_USE_ERROR
    assert results[1]["tool_use_id"] == "tu-2"


@pytest.mark.parametrize("reason", ["max_tokens", "pause_turn"])
async def test_handle_continue_persists_and_broadcasts(broadcast, reason):
    check_cancelled = MagicMock()

    mock_persist = await _run_handle_continue(
        reason, broadcast,
        response=build_assistant_message(reason),
        check_cancelled=check_cancelled,
    )

    check_cancelled.assert_called_once()

    mock_persist.assert_awaited_once()
    assert mock_persist.call_args[1]["session_id"] == "sess-1"
    persisted = _persisted(mock_persist)
    assert persisted["role"] == "user"
    assert len(persisted["content"]) == 1
    assert persisted["content"][0]["text"] == CONTINUE_MESSAGES[reason]

    broadcast.assert_awaited_once()
    event: BroadcastEvent = broadcast.call_args[0][0]
    assert event.type == "tool_result"
    assert event.role == "user"
    assert event.session_id == "sess-1"
    assert len(event.content) == 1
    assert event.content[0]["text"] == CONTINUE_MESSAGES[reason]


async def test_handle_continue_no_response_still_works(broadcast):
    """When response is None (backward compat), just inject continuation text."""
    mock_persist = await _run_handle_continue("max_tokens", broadcast)

    persisted = _persisted(mock_persist)
    assert len(persisted["content"]) == 1
    assert persisted["content"][0]["text"] == CONTINUE_MESSAGES["max_tokens"]


async def test_handle_continue_max_tokens_with_tool_use_injects_tool_results(broadcast):
    """When max_tokens truncates a response mid-tool-call, synthetic error
    tool_results must be injected so the API doesn't reject the next request."""
    response = build_assistant_message(
        "max_tokens",
        content=[
            TextBlock(type="text", text="Let me call that tool"),
            ToolUseBlock(type="tool_use", id="tu-abc", name="cat", input={"paths": ["x.py"]}),
        ],
    )

    mock_persist = await _run_handle_continue("max_tokens", broadcast, response=response)

    persisted = _persisted(mock_persist)
    assert persisted["role"] == "user"
    assert len(persisted["content"]) == 2
    assert persisted["content"][0]["type"] == "tool_result"
    assert persisted["content"][0]["tool_use_id"] == "tu-abc"
    assert persisted["content"][0]["is_error"] is True
    assert persisted["content"][0]["content"][0]["text"] == TRUNCATED_TOOL_USE_ERROR
    assert persisted["content"][1]["type"] == "text"
    assert persisted["content"][1]["text"] == CONTINUE_MESSAGES["max_tokens"]

    event: BroadcastEvent = broadcast.call_args[0][0]
    assert len(event.content) == 2
    assert event.content[0]["type"] == "tool_result"
    assert event.content[1]["text"] == CONTINUE_MESSAGES["max_tokens"]


async def test_handle_continue_max_tokens_multiple_tool_use_blocks(broadcast):
    """All tool_use blocks in the truncated response get error tool_results."""
    response = build_assistant_message(
        "max_tokens",
        content=[
            ToolUseBlock(type="tool_use", id="tu-1", name="tool_a", input={}),
            ToolUseBlock(type="tool_use", id="tu-2", name="tool_b", input={}),
        ],
    )

    mock_persist = await _run_handle_continue("max_tokens", broadcast, response=response)

    persisted = _persisted(mock_persist)
    assert len(persisted["content"]) == 3
    assert persisted["content"][0]["tool_use_id"] == "tu-1"
    assert persisted["content"][1]["tool_use_id"] == "tu-2"
    assert persisted["content"][2]["type"] == "text"


async def test_handle_continue_checks_cancelled_before_persisting(broadcast):
    def raise_interrupt():
        raise UserInterrupt()

    with patch(
        "hypergolic.messages.conversation.stop_reasons.persist_messages",
        new=AsyncMock(),
    ) as mock_persist:
        with pytest.raises(UserInterrupt):
            await handle_continue(
                "max_tokens", build_session(sid="sess-1", project_path="/tmp/test"),
                broadcast, raise_interrupt,
            )

    mock_persist.assert_not_awaited()
    broadcast.assert_not_awaited()


async def test_handle_continue_unknown_reason_raises_key_error(broadcast):
    with pytest.raises(KeyError):
        await _run_handle_continue("unknown_reason", broadcast)
