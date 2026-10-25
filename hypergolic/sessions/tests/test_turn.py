import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import MessageParam

from hypergolic.messages.types import UserInterrupt
from hypergolic.sessions.turn import run_session_turn

TURN = "hypergolic.sessions.turn"
_ASYNC = {"create_message", "finalize_turn", "set_session_status_and_broadcast"}
_PATCHED = (
    "load_session", "create_message", "finalize_turn", "resolve_repo_and_base",
    "get_git_status", "set_session_status_and_broadcast", "persist_error_message",
    "persist_error", "fail_dispatch_if_child",
)


@pytest.fixture
def turn():
    mocks = {
        name: patch(f"{TURN}.{name}", new_callable=AsyncMock if name in _ASYNC else MagicMock)
        for name in _PATCHED
    }
    started = {name: p.start() for name, p in mocks.items()}
    ns = SimpleNamespace(**started, notify=AsyncMock())

    async def run() -> dict:
        user: MessageParam = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
        await run_session_turn(
            "s-1", user, asyncio.Event(), ns.notify, AsyncMock(), AsyncMock(),
        )
        return ns.notify.call_args[0][0]

    ns.run = run
    yield ns
    for p in mocks.values():
        p.stop()


async def test_successful_turn(turn):
    # The done-event status must diff against the endpoint's base rev
    # (origin/<base> in a live clone), not the local base branch name.
    turn.resolve_repo_and_base.return_value = ("/tmp", "origin/main")
    turn.get_git_status.return_value = MagicMock(model_dump=lambda: {"branch": "main"})

    sent = await turn.run()

    turn.create_message.assert_called_once()
    turn.finalize_turn.assert_called_once()
    turn.get_git_status.assert_called_once_with(
        repo="/tmp", session_id="s-1", base_branch="origin/main",
    )
    assert sent["type"] == "done"
    assert sent["git_status"] == {"branch": "main"}


async def test_successful_turn_git_fails(turn):
    turn.resolve_repo_and_base.side_effect = Exception("no session")

    sent = await turn.run()

    assert sent["type"] == "done"
    assert "git_status" not in sent


async def test_user_interrupt(turn):
    turn.create_message.side_effect = UserInterrupt(partial_text="partial...")

    sent = await turn.run()

    assert sent["type"] == "interrupted"
    assert sent["partial_text"] == "partial..."


async def test_user_interrupt_no_partial(turn):
    turn.create_message.side_effect = UserInterrupt()

    sent = await turn.run()

    assert sent["type"] == "interrupted"
    assert "partial_text" not in sent


async def test_user_interrupt_send_fails(turn):
    turn.create_message.side_effect = UserInterrupt()
    turn.notify.side_effect = Exception("ws closed")

    await turn.run()


async def test_error_during_turn(turn):
    turn.create_message.side_effect = RuntimeError("model exploded")

    sent = await turn.run()

    assert sent["type"] == "error"
    assert "model exploded" in sent["detail"]
    turn.persist_error_message.assert_called_once()
    turn.persist_error.assert_called_once()
    turn.fail_dispatch_if_child.assert_called_once()


async def test_unloadable_session_reports_instead_of_raising(turn):
    """A resumed turn has no caller to catch this — it must land in the session."""
    turn.load_session.side_effect = RuntimeError("project is gone")

    sent = await turn.run()

    assert sent["type"] == "error"
    assert "project is gone" in sent["detail"]
    turn.create_message.assert_not_called()
    turn.persist_error_message.assert_called_once()


async def test_error_during_turn_send_fails(turn):
    turn.create_message.side_effect = RuntimeError("boom")
    turn.notify.side_effect = Exception("ws closed")

    await turn.run()
