"""Tests for hypergolic.dispatch.lifecycle."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from anthropic.types import Message, TextBlock, Usage

from hypergolic.dispatch.lifecycle import (
    _extract_final_text,
    auto_conclude_if_needed,
    cancel_child_dispatches,
    fail_dispatch_if_child,
)
from hypergolic.dispatch.state import (
    DispatchResult,
    _child_to_parent,
    _finalize_on_auto_conclude,
    _pending_dispatches,
)
from hypergolic.enums import SessionStatus
from hypergolic.dispatch.conclude import BranchPreservationError
from hypergolic.dispatch.lifecycle import _teardown_for_auto_conclude


def _clear():
    _pending_dispatches.clear()
    _child_to_parent.clear()
    _finalize_on_auto_conclude.clear()


def _make_message(text: str = "hello") -> Message:
    return Message(
        id="msg-1",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
        model="claude-3-5-sonnet-20241022",
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


# ── _extract_final_text ──────────────────────────────────────────────────


def test_extract_final_text_with_text_block():
    assert "My final answer" in _extract_final_text(_make_message("My final answer"))


def test_extract_final_text_no_text_blocks():
    msg = Message(
        id="m", type="message", role="assistant", content=[],
        model="claude", stop_reason="end_turn", stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )
    assert _extract_final_text(msg) == "<no text content>"


def test_extract_final_text_multiple_blocks():
    msg = Message(
        id="m", type="message", role="assistant",
        content=[TextBlock(type="text", text="A"), TextBlock(type="text", text="B")],
        model="claude", stop_reason="end_turn", stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )
    result = _extract_final_text(msg)
    assert "A" in result and "B" in result


# ── auto_conclude_if_needed ───────────────────────────────────────────────


async def _noop_broadcast(event):
    pass


async def test_auto_conclude_no_parent():
    _clear()
    assert await auto_conclude_if_needed("s1", None, _make_message(), _noop_broadcast) is False


async def test_auto_conclude_no_pending_future():
    _clear()
    assert await auto_conclude_if_needed("s1", "parent-1", _make_message(), _noop_broadcast) is False


async def test_auto_conclude_future_already_done():
    _clear()
    try:
        future = asyncio.get_running_loop().create_future()
        future.set_result(DispatchResult(outcome="success", conclusion="done"))
        _pending_dispatches["done-child"] = future
        assert await auto_conclude_if_needed("done-child", "parent", _make_message(), _noop_broadcast) is False
    finally:
        _clear()


async def test_auto_conclude_send_turn_child_stays_live():
    """send_turn children (not marked finalize) resolve but are not concluded."""
    _clear()
    try:
        future = asyncio.get_running_loop().create_future()
        _pending_dispatches["child-3"] = future
        with (
            patch("hypergolic.dispatch.lifecycle.set_session_status_and_broadcast") as set_status,
            patch("hypergolic.dispatch.lifecycle._teardown_for_auto_conclude") as teardown,
        ):
            result = await auto_conclude_if_needed(
                "child-3", "parent-1", _make_message("the final message"), _noop_broadcast
            )
        assert result is True
        dr = future.result()
        assert dr.outcome == "success"
        assert "child-3" in dr.conclusion
        assert "the final message" in dr.conclusion
        assert dr.auto_concluded is True
        assert dr.reply_text == "the final message"
        assert dr.worktree_branch is None
        set_status.assert_not_called()
        teardown.assert_not_called()
    finally:
        _clear()


async def test_auto_conclude_dispatch_child_is_finalized():
    """dispatch() children get the full conclude lifecycle on auto-conclude."""
    _clear()
    events = []

    async def broadcast(event):
        events.append(event)

    try:
        future = asyncio.get_running_loop().create_future()
        _pending_dispatches["child-4"] = future
        _finalize_on_auto_conclude.add("child-4")
        with (
            patch(
                "hypergolic.dispatch.lifecycle._teardown_for_auto_conclude",
                new=AsyncMock(return_value="branch-x"),
            ) as teardown,
            patch(
                "hypergolic.dispatch.lifecycle.set_session_status_and_broadcast",
                new=AsyncMock(),
            ) as set_status,
            patch("hypergolic.dispatch.lifecycle.set_concluded_at") as set_concluded,
            patch("hypergolic.dispatch.lifecycle.schedule_session_sandbox_cleanup") as cleanup,
        ):
            result = await auto_conclude_if_needed(
                "child-4", "parent-1", _make_message("done here"), broadcast
            )
        assert result is True
        dr = future.result()
        assert dr.auto_concluded is True
        assert dr.worktree_branch == "branch-x"
        teardown.assert_awaited_once_with("child-4")
        set_status.assert_awaited_once()
        assert set_status.await_args is not None
        assert set_status.await_args.args[1] == SessionStatus.CONCLUDED
        set_concluded.assert_called_once_with("child-4")
        cleanup.assert_called_once_with("child-4")
        assert [e.type for e in events] == ["dispatch_concluded"]
        assert "child-4" not in _finalize_on_auto_conclude
    finally:
        _clear()


async def test_teardown_for_auto_conclude_unpreservable_branch_proceeds():
    """No agent to bounce to: a failed fetch-back is logged, not raised,
    and the branch is not claimed to survive."""
    session = object()
    calls = []

    async def fake_teardown(sess, *, delete_worktree, delete_branch_flag):
        calls.append((delete_worktree, delete_branch_flag))
        raise BranchPreservationError("fetch failed")

    with (
        patch("hypergolic.dispatch.lifecycle.load_session", return_value=session),
        patch(
            "hypergolic.dispatch.lifecycle.teardown_worktree_at_conclude",
            new=fake_teardown,
        ),
    ):
        branch = await _teardown_for_auto_conclude("child-5")
    assert branch is None
    assert calls == [(True, False)]


# ── fail_dispatch_if_child ──────────────────────────────────────────────────


def test_fail_dispatch_no_parent():
    _clear()
    assert fail_dispatch_if_child("orphan", "error", AsyncMock()) is False


async def test_fail_dispatch_with_parent_fails_the_call_then_ends_the_child():
    _clear()
    future = asyncio.get_running_loop().create_future()
    _pending_dispatches["child-fail"] = future
    _child_to_parent["child-fail"] = "parent-fail"
    broadcast = AsyncMock()
    try:
        with patch("hypergolic.dispatch.child_end.end_child", new_callable=AsyncMock) as end:
            result = fail_dispatch_if_child("child-fail", "DB crashed", broadcast)
            await asyncio.sleep(0)

        assert result is True
        dr = future.result()
        assert dr.outcome == "failure"
        assert "DB crashed" in dr.conclusion
        # Same cleanup as `dispatch --conclude`, but the child keeps ERROR.
        end.assert_awaited_once_with("child-fail", broadcast, status=SessionStatus.ERROR)
    finally:
        _clear()


async def test_fail_dispatch_keeps_a_conducted_child_live():
    _clear()
    future = asyncio.get_running_loop().create_future()
    _pending_dispatches["child-eval"] = future
    _child_to_parent["child-eval"] = "parent-eval"
    try:
        with (
            patch("hypergolic.dispatch.lifecycle.load_conducted_by", return_value="parent-eval"),
            patch("hypergolic.dispatch.child_end.end_child", new_callable=AsyncMock) as end,
        ):
            assert fail_dispatch_if_child("child-eval", "HTTP 504", AsyncMock()) is True
            await asyncio.sleep(0)
        assert future.result().outcome == "failure"
        end.assert_not_awaited()
    finally:
        _clear()


# ── cancel_child_dispatches ────────────────────────────────────────────────


def test_cancel_interrupts_children():
    _clear()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        _pending_dispatches["child-c"] = future
        _child_to_parent["child-c"] = "parent-c"

        with (
            patch("hypergolic.dispatch.lifecycle.set_session_status") as mock_status,
            patch("hypergolic.dispatch.lifecycle.schedule_session_sandbox_cleanup"),
            patch("hypergolic.dispatch.lifecycle._teardown_child_worktree", new_callable=AsyncMock),
        ):
            loop.run_until_complete(cancel_child_dispatches("parent-c"))

        dr = future.result()
        assert dr.outcome == "suppressed"
        assert "child-c" not in _pending_dispatches
        mock_status.assert_called_once_with("child-c", SessionStatus.INTERRUPTED)
    finally:
        loop.close()
        _clear()


def test_cancel_noop_when_no_children():
    _clear()
    asyncio.run(cancel_child_dispatches("parent-with-no-children"))  # must not raise


def test_cancel_swallows_teardown_errors():
    _clear()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        _pending_dispatches["child-err"] = future
        _child_to_parent["child-err"] = "parent-err"

        with (
            patch("hypergolic.dispatch.lifecycle.set_session_status"),
            patch("hypergolic.dispatch.lifecycle.schedule_session_sandbox_cleanup"),
            patch("hypergolic.dispatch.lifecycle._teardown_child_worktree", new_callable=AsyncMock, side_effect=RuntimeError("boom")),
        ):
            try:
                loop.run_until_complete(cancel_child_dispatches("parent-err"))
            except RuntimeError:
                pytest.fail("cancel_child_dispatches must not propagate teardown errors")

        assert future.result().outcome == "suppressed"
    finally:
        loop.close()
        _clear()
