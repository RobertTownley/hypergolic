import asyncio
from unittest.mock import MagicMock, patch

import pytest

from hypergolic.websocket.resume import resume_interrupted_sessions


async def test_resumes_each_claimed_session_without_adding_a_message():
    start_turn = MagicMock()

    with patch(
        "hypergolic.websocket.resume.claim_resumable_sessions",
        return_value=["s-1", "s-2"],
    ):
        await resume_interrupted_sessions(start_turn)

    assert [c.args for c in start_turn.call_args_list] == [("s-1", None), ("s-2", None)]


async def test_a_failed_resume_is_re_flagged_for_the_next_connection():
    start_turn = MagicMock(side_effect=RuntimeError("no runner"))

    with (
        patch(
            "hypergolic.websocket.resume.claim_resumable_sessions",
            return_value=["s-1", "s-2"],
        ),
        patch("hypergolic.websocket.resume.set_session_resume") as mock_set,
    ):
        await resume_interrupted_sessions(start_turn)

    assert [c.args for c in mock_set.call_args_list] == [("s-1", True), ("s-2", True)]


async def test_cancellation_hands_back_every_unstarted_session():
    start_turn = MagicMock(side_effect=asyncio.CancelledError())

    with (
        patch(
            "hypergolic.websocket.resume.claim_resumable_sessions",
            return_value=["s-1", "s-2", "s-3"],
        ),
        patch("hypergolic.websocket.resume.set_session_resume") as mock_set,
        pytest.raises(asyncio.CancelledError),
    ):
        await resume_interrupted_sessions(start_turn)

    assert [c.args[0] for c in mock_set.call_args_list] == ["s-1", "s-2", "s-3"]


async def test_claim_failure_does_not_break_the_connection():
    start_turn = MagicMock()

    with patch(
        "hypergolic.websocket.resume.claim_resumable_sessions",
        side_effect=RuntimeError("db down"),
    ):
        await resume_interrupted_sessions(start_turn)

    start_turn.assert_not_called()
