from unittest.mock import AsyncMock, patch

import pytest
from hypergolic.enums import SessionStatus
from hypergolic.messages.conversation.loop import create_message
from tests._factories import build_assistant_message, build_session
from tests.conftest import make_project, make_session

def _seed(sid="s1", parent_id=None):
    make_project("p1", "Proj", "/tmp/p")
    if parent_id:
        make_session("p1", parent_id)
    make_session("p1", sid, parent_id=parent_id)


def _make_session(sid="s1", parent_id=None):
    return build_session(sid=sid, project_id="p1", project_path="/tmp/p", parent_id=parent_id)


def _make_response(stop_reason="end_turn"):
    return build_assistant_message(stop_reason, text="Done")


async def test_loop_breaks_on_terminal_status_after_tool_use(broadcast):
    _seed("child", parent_id="parent")
    session = _make_session("child", parent_id="parent")

    tool_use_response = _make_response(stop_reason="tool_use")
    stream_call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal stream_call_count
        stream_call_count += 1
        return tool_use_response

    with (
        patch("hypergolic.messages.conversation.loop.frozen_prompt_blocks", new=AsyncMock(return_value=[])),
        patch("hypergolic.messages.conversation.loop.live_prompt_blocks", new=AsyncMock(return_value=[])),
        patch("hypergolic.messages.conversation.loop.persist_messages", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.persist_agent_message", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.maybe_generate_description"),
        patch("hypergolic.messages.conversation.loop.should_truncate", return_value=False),
        patch("hypergolic.messages.conversation.loop.set_session_status_and_broadcast", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.load_session_messages", return_value=[]),
        patch("hypergolic.messages.conversation.loop.stream_response", new=AsyncMock(side_effect=mock_stream)),
        patch("hypergolic.messages.conversation.loop.dispatch_stop_reason", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.get_session_status", return_value=SessionStatus.CONCLUDED),
        patch("hypergolic.messages.conversation.loop.auto_conclude_if_needed", new=AsyncMock(return_value=False)),
    ):
        result = await create_message(
            session=session,
            message={"role": "user", "content": [{"type": "text", "text": "hi"}]},
            broadcast=broadcast,
        )

    assert stream_call_count == 1
    assert result == tool_use_response


async def test_loop_raises_on_null_stop_reason(broadcast):
    _seed("s2")
    session = _make_session("s2")

    null_stop_response = _make_response(stop_reason=None)

    with (
        patch("hypergolic.messages.conversation.loop.frozen_prompt_blocks", new=AsyncMock(return_value=[])),
        patch("hypergolic.messages.conversation.loop.live_prompt_blocks", new=AsyncMock(return_value=[])),
        patch("hypergolic.messages.conversation.loop.persist_messages", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.persist_agent_message", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.maybe_generate_description"),
        patch("hypergolic.messages.conversation.loop.should_truncate", return_value=False),
        patch("hypergolic.messages.conversation.loop.set_session_status_and_broadcast", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.load_session_messages", return_value=[]),
        patch("hypergolic.messages.conversation.loop.stream_response", new=AsyncMock(return_value=null_stop_response)),
        patch("hypergolic.messages.conversation.loop.get_session_status", return_value=SessionStatus.THINKING),
    ):
        with pytest.raises(RuntimeError, match="no stop_reason"):
            await create_message(
                session=session,
                message={"role": "user", "content": [{"type": "text", "text": "hi"}]},
                broadcast=broadcast,
            )


async def test_loop_continues_when_status_is_not_terminal(broadcast):
    _seed("s1")
    session = _make_session("s1")

    tool_use_response = _make_response(stop_reason="tool_use")
    end_turn_response = _make_response(stop_reason="end_turn")
    stream_call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal stream_call_count
        stream_call_count += 1
        if stream_call_count == 1:
            return tool_use_response
        return end_turn_response

    with (
        patch("hypergolic.messages.conversation.loop.frozen_prompt_blocks", new=AsyncMock(return_value=[])),
        patch("hypergolic.messages.conversation.loop.live_prompt_blocks", new=AsyncMock(return_value=[])),
        patch("hypergolic.messages.conversation.loop.persist_messages", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.persist_agent_message", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.maybe_generate_description"),
        patch("hypergolic.messages.conversation.loop.should_truncate", return_value=False),
        patch("hypergolic.messages.conversation.loop.set_session_status_and_broadcast", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.load_session_messages", return_value=[]),
        patch("hypergolic.messages.conversation.loop.stream_response", new=AsyncMock(side_effect=mock_stream)),
        patch("hypergolic.messages.conversation.loop.dispatch_stop_reason", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.get_session_status", return_value=SessionStatus.TOOL_USE),
        patch("hypergolic.messages.conversation.loop.auto_conclude_if_needed", new=AsyncMock(return_value=False)),
    ):
        result = await create_message(
            session=session,
            message={"role": "user", "content": [{"type": "text", "text": "hi"}]},
            broadcast=broadcast,
        )

    assert stream_call_count == 2
    assert result == end_turn_response


async def test_resumed_turn_persists_no_new_message(broadcast):
    _seed("s3")
    session = _make_session("s3")

    with (
        patch("hypergolic.messages.conversation.loop.frozen_prompt_blocks", new=AsyncMock(return_value=[])),
        patch("hypergolic.messages.conversation.loop.live_prompt_blocks", new=AsyncMock(return_value=[])),
        patch("hypergolic.messages.conversation.loop.persist_messages", new=AsyncMock()) as mock_persist,
        patch("hypergolic.messages.conversation.loop.persist_agent_message", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.maybe_generate_description") as mock_describe,
        patch("hypergolic.messages.conversation.loop.should_truncate", return_value=False),
        patch("hypergolic.messages.conversation.loop.set_session_status_and_broadcast", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.load_session_messages", return_value=[]),
        patch("hypergolic.messages.conversation.loop.stream_response", new=AsyncMock(return_value=_make_response())),
        patch("hypergolic.messages.conversation.loop.dispatch_stop_reason", new=AsyncMock()),
        patch("hypergolic.messages.conversation.loop.get_session_status", return_value=SessionStatus.THINKING),
        patch("hypergolic.messages.conversation.loop.auto_conclude_if_needed", new=AsyncMock(return_value=False)),
    ):
        await create_message(
            session=session, message=None, broadcast=broadcast,
        )

    mock_persist.assert_not_called()
    mock_describe.assert_not_called()
