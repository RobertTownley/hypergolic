"""Tests for hypergolic.messages.conversation.dispatch."""

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import StopReason

from hypergolic.messages.conversation.dispatch import (
    broadcast_response,
    dispatch_stop_reason,
)
from hypergolic.messages.types import BroadcastEvent, ModelRefusal, UserInterrupt
from tests._factories import build_assistant_message, build_session


@pytest.fixture
def session():
    return build_session(sid="sess-1", project_path="/tmp/test")


def _dispatch(reason: Any, response, session, broadcast):
    return dispatch_stop_reason(
        cast(StopReason, reason), response, "db-msg-1", [], session, broadcast,
        None, MagicMock(),
    )


def _patch(name: str, mock):
    return patch(f"hypergolic.messages.conversation.dispatch.{name}", new=mock)


async def test_broadcast_response(broadcast):
    await broadcast_response(build_assistant_message(), "db-msg-1", "sess-1", broadcast)

    broadcast.assert_awaited_once()
    event: BroadcastEvent = broadcast.call_args[0][0]
    assert event.type == "assistant_message"
    assert event.role == "assistant"
    assert event.session_id == "sess-1"
    assert event.model == "claude-sonnet-4-20250514"
    assert event.stop_reason == "end_turn"
    assert event.message_id == "db-msg-1"
    assert event.usage is not None
    assert event.usage["input_tokens"] == 10
    assert event.usage["output_tokens"] == 20


async def test_broadcast_response_no_usage(broadcast):
    response = build_assistant_message()
    response.__dict__["usage"] = None

    await broadcast_response(response, "db-msg-1", "sess-1", broadcast)

    assert broadcast.call_args[0][0].usage is None


async def test_broadcast_response_with_tool_display_names(broadcast):
    await broadcast_response(
        build_assistant_message(), "db-msg-1", "sess-1", broadcast, {"tool-1": "My Tool"}
    )

    broadcast.assert_awaited_once()


async def test_dispatch_end_turn(broadcast, session):
    """end_turn just broadcasts the response, nothing else."""
    await _dispatch("end_turn", build_assistant_message(), session, broadcast)

    broadcast.assert_awaited_once()


async def test_dispatch_tool_use(broadcast, session):
    result = MagicMock()
    result.message = {"content": [], "role": "user"}

    with _patch("handle_tool_use_stop", AsyncMock(return_value=result)) as mock_handle:
        await _dispatch("tool_use", build_assistant_message("tool_use"), session, broadcast)

    mock_handle.assert_awaited_once()


@pytest.mark.parametrize("reason", ["max_tokens", "pause_turn"])
async def test_dispatch_continue_reasons(broadcast, session, reason):
    response = build_assistant_message(reason)

    with _patch("handle_continue", AsyncMock()) as mock_handle:
        await _dispatch(reason, response, session, broadcast)

    mock_handle.assert_awaited_once()
    assert mock_handle.call_args[0][0] == reason
    assert mock_handle.call_args[1]["response"] is response


async def test_dispatch_refusal_with_details(broadcast, session):
    from anthropic.types.refusal_stop_details import RefusalStopDetails

    response = build_assistant_message("refusal")
    response.__dict__["stop_details"] = RefusalStopDetails(
        type="refusal", category="cyber", explanation="Declined for cyber harm."
    )
    with pytest.raises(ModelRefusal, match="category: cyber.*Declined for cyber harm"):
        await _dispatch("refusal", response, session, broadcast)
    broadcast.assert_awaited_once()


async def test_dispatch_refusal_without_details(broadcast, session):
    with pytest.raises(ModelRefusal, match="Model refused to respond"):
        await _dispatch("refusal", build_assistant_message("refusal"), session, broadcast)


async def test_dispatch_unhandled_stop_reason(broadcast, session):
    with pytest.raises(Exception, match="Unhandled stop reason: weird_reason"):
        await _dispatch("weird_reason", build_assistant_message(), session, broadcast)


@pytest.mark.parametrize(
    "side_effect, raises, persists_interrupt",
    [
        (UserInterrupt(), UserInterrupt, True),
        (asyncio.CancelledError(), UserInterrupt, True),
        (RuntimeError("boom"), RuntimeError, False),
    ],
    ids=["interrupt", "cancelled", "exception"],
)
async def test_dispatch_tool_use_failure(
    broadcast, session, side_effect, raises, persists_interrupt
):
    """Interrupt/cancel during tool_use synthesizes 'Interrupted by user'
    tool_results; generic exceptions must NOT — the load-time repair layer
    backfills orphaned tool_uses with a proper error label on the next turn,
    and persisting here would (a) mislabel real crashes as user interrupts and
    (b) duplicate tool_results when the error happens after handle_tool_use_stop
    has already persisted real ones. All failure paths drop pending workflow
    context actions so a half-completed transition doesn't leak into the next
    turn."""
    response = build_assistant_message("tool_use")

    with (
        _patch("handle_tool_use_stop", AsyncMock(side_effect=side_effect)),
        _patch("persist_interrupt_tool_results", AsyncMock()) as mock_persist,
        _patch("discard_pending_context_actions", MagicMock()) as mock_discard,
    ):
        with pytest.raises(raises):
            await _dispatch("tool_use", response, session, broadcast)

    mock_discard.assert_called_once_with(session.id)
    if persists_interrupt:
        mock_persist.assert_awaited_once_with(session.id, response)
    else:
        mock_persist.assert_not_awaited()


async def test_dispatch_end_turn_interrupted_no_persist(session):
    broadcast = AsyncMock(side_effect=UserInterrupt())

    with _patch("persist_interrupt_tool_results", AsyncMock()) as mock_persist:
        with pytest.raises(UserInterrupt):
            await _dispatch("end_turn", build_assistant_message(), session, broadcast)

    mock_persist.assert_not_awaited()


@pytest.mark.parametrize(
    "side_effect, raises",
    [(UserInterrupt(), UserInterrupt), (RuntimeError("oops"), RuntimeError)],
    ids=["interrupt", "exception"],
)
async def test_dispatch_continue_failure_no_persist(broadcast, session, side_effect, raises):
    with (
        _patch("handle_continue", AsyncMock(side_effect=side_effect)),
        _patch("persist_interrupt_tool_results", AsyncMock()) as mock_persist,
    ):
        with pytest.raises(raises):
            await _dispatch(
                "max_tokens", build_assistant_message("max_tokens"), session, broadcast
            )

    mock_persist.assert_not_awaited()
