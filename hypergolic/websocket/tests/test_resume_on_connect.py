import threading
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from hypergolic.sessions.resume import set_session_resume
from tests.conftest import make_message, make_project, make_session


def _flagged_session() -> str:
    make_project("proj-1")
    session = make_session(sid="s-resume")
    make_message(
        session,
        role="assistant",
        content=[{"type": "tool_use", "id": "tu-1", "name": "cmd", "input": {}}],
    )
    set_session_resume(session, True)
    return session


@contextmanager
def _recorded_turns(started: threading.Event):
    with (
        patch("hypergolic.websocket.router.verify_token", return_value=True),
        patch("hypergolic.websocket.router.register_turn_runner"),
        patch(
            "hypergolic.websocket.router.run_session_turn",
            new_callable=AsyncMock,
            side_effect=lambda *a, **kw: started.set(),
        ) as mock_turn,
    ):
        yield mock_turn


def test_connecting_resumes_a_flagged_session(api_client):
    session = _flagged_session()
    started = threading.Event()

    with _recorded_turns(started) as mock_turn:
        with api_client.websocket_connect("/ws"):
            assert started.wait(timeout=5.0)

    assert mock_turn.await_args is not None
    session_id, message = mock_turn.await_args.args[:2]
    assert session_id == session
    assert message is None


def test_connecting_twice_resumes_only_once(api_client):
    _flagged_session()
    started = threading.Event()

    with _recorded_turns(started) as mock_turn:
        with api_client.websocket_connect("/ws"):
            assert started.wait(timeout=5.0)
        with api_client.websocket_connect("/ws"):
            pass

    assert mock_turn.await_count == 1
