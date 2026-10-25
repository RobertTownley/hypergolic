"""Conducted children (`dispatch --eval`): an end of turn returns, `reply` continues."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hypergolic.dispatch import runner
from hypergolic.dispatch import state as dispatch_state
from hypergolic.dispatch.state import (
    DispatchResult,
    _child_to_parent,
    _pending_dispatches,
    resolve_dispatch,
)
from hypergolic.enums import SessionStatus
from hypergolic.tools import approval_delegate

CHILD = "child-c"
PARENT = "parent-c"


@pytest.fixture(autouse=True)
def _clean():
    yield
    approval_delegate.close(CHILD)
    _pending_dispatches.pop(CHILD, None)
    _child_to_parent.pop(CHILD, None)


def _child(conducted_by: str | None = PARENT):
    return SimpleNamespace(base_branch="pin/abc", conducted_by=conducted_by)


def _end_turn(text: str) -> DispatchResult:
    return DispatchResult(outcome="success", conclusion="ended", auto_concluded=True, reply_text=text)


async def _reply(turn_runner, status=SessionStatus.IDLE, parent=PARENT, child=None):
    with (
        patch.object(dispatch_state, "_turn_runner", turn_runner),
        patch.object(runner, "load_session", return_value=child or _child()),
        patch.object(runner, "get_session_status", return_value=status),
        patch.object(runner, "load_conducted_by", return_value=(child or _child()).conducted_by),
    ):
        return await runner.reply_to_child(CHILD, parent, "one retry is enough")


async def test_reply_sends_the_next_user_turn_and_waits_again():
    sent: list[tuple[str, dict]] = []

    def turn_runner(session_id, message):
        sent.append((session_id, message))
        asyncio.get_running_loop().call_soon(resolve_dispatch, session_id, _end_turn("which retry count?"))

    result = await _reply(turn_runner)
    assert sent[0][0] == CHILD
    assert sent[0][1]["content"][0]["text"] == "one retry is enough"
    assert result.auto_concluded and result.conducted and result.reply_text == "which retry count?"


async def test_a_failed_turn_can_be_continued():
    sent: list[str] = []

    def turn_runner(session_id, message):
        sent.append(session_id)
        asyncio.get_running_loop().call_soon(resolve_dispatch, session_id, _end_turn("done"))

    result = await _reply(turn_runner, status=SessionStatus.ERROR)
    assert sent == [CHILD] and result.auto_concluded


async def test_a_concluded_child_takes_no_reply():
    result = await _reply(lambda *_: None, status=SessionStatus.CONCLUDED)
    assert result.outcome == "failure" and "concluded" in result.conclusion


@pytest.mark.parametrize("parent,conducted_by", [("someone-else", PARENT), (PARENT, None)])
async def test_only_the_conducting_parent_can_reply(parent, conducted_by):
    result = await _reply(lambda *_: None, parent=parent, child=_child(conducted_by))
    assert result.outcome == "failure" and "not a conducted child" in result.conclusion
