import asyncio
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocketDisconnect

from hypergolic.websocket import router as router_mod
from hypergolic.websocket.hub import ConnectionHub
from hypergolic.websocket.router import websocket_endpoint
from hypergolic.websocket.turn_manager import TurnManager
from hypergolic.messages.types import BroadcastEvent


@pytest.fixture(autouse=True)
def _fresh_globals():
    """Isolate the process-global hub/manager per test."""
    hub = ConnectionHub()
    tm = TurnManager()
    with (
        patch.object(router_mod, "get_hub", return_value=hub),
        patch.object(router_mod, "get_turn_manager", return_value=tm),
        patch.object(router_mod, "resume_interrupted_sessions", new_callable=AsyncMock),
    ):
        yield hub, tm


async def test_unauthorized():
    ws = AsyncMock()
    ws.cookies = {"h_token": "bad"}

    with patch("hypergolic.websocket.router.verify_token", return_value=False):
        await websocket_endpoint(ws)

    ws.close.assert_called_once_with(code=4003, reason="Unauthorized")
    ws.accept.assert_not_called()


async def test_unauthorized_no_token():
    ws = AsyncMock()
    ws.cookies = {}

    with patch("hypergolic.websocket.router.verify_token", return_value=False):
        await websocket_endpoint(ws)

    ws.close.assert_called_once_with(code=4003, reason="Unauthorized")


@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_disconnect(mock_verify):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}
    ws.receive_json.side_effect = WebSocketDisconnect()

    await websocket_endpoint(ws)

    ws.accept.assert_called_once()


@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_unexpected_error(mock_verify):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}
    ws.receive_json.side_effect = RuntimeError("boom")

    await websocket_endpoint(ws)

    ws.accept.assert_called_once()


@patch("hypergolic.websocket.router.handle_conclude_session", new_callable=AsyncMock)
@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_conclude_message(mock_verify, mock_conclude):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}
    ws.receive_json.side_effect = [
        {"type": "conclude_session", "session_id": "s-1", "rating": 5},
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(ws)
    mock_conclude.assert_called_once()


@patch("hypergolic.websocket.router.resolve_approval_response")
@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_approval_message(mock_verify, mock_resolve):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}
    ws.receive_json.side_effect = [
        {"type": "tool_approval_response", "tool_use_id": "tu-1", "approved": True},
        WebSocketDisconnect(),
    ]

    await websocket_endpoint(ws)
    mock_resolve.assert_called_once()


@patch("hypergolic.websocket.router.handle_connect", new_callable=AsyncMock)
@patch("hypergolic.websocket.router.cancel_child_dispatches")
@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_chat_message(mock_verify, mock_cancel, mock_connect):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}

    call_count = [0]
    async def receive_json_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            return {"type": "chat", "message": "hello", "session_id": "s-1"}
        await asyncio.sleep(0.05)
        raise WebSocketDisconnect()

    ws.receive_json = receive_json_side_effect

    await websocket_endpoint(ws)

    mock_cancel.assert_called_once_with("s-1")
    mock_connect.assert_called_once()


@patch("hypergolic.websocket.router.handle_connect", new_callable=AsyncMock)
@patch("hypergolic.websocket.router.cancel_child_dispatches")
@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_chat_new_session(mock_verify, mock_cancel, mock_connect):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}

    call_count = [0]
    async def receive_json_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            return {"type": "chat", "message": "hello", "project_id": "p-1"}
        await asyncio.sleep(0.05)
        raise WebSocketDisconnect()

    ws.receive_json = receive_json_side_effect

    await websocket_endpoint(ws)

    # Unique placeholder per new-session request: a shared key would let one
    # tab's new-session turn cancel another's on the global manager.
    target = mock_cancel.call_args[0][0]
    assert target.startswith("__new__")
    assert target != "__new__"


@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_close_failure_swallowed(mock_verify):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}
    ws.receive_json.side_effect = WebSocketDisconnect()
    ws.close.side_effect = Exception("already closed")

    await websocket_endpoint(ws)


@patch("hypergolic.websocket.router.serialize_event", return_value={"type": "t"})
@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_broadcast_fans_out_via_hub(mock_verify, mock_serial):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}

    async def fake_handle_connect(req, cancel_event, notify, broadcast, approval_callback):
        await broadcast(BroadcastEvent(type="test", role="system", content=[]))

    call_count = [0]
    async def receive_json_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            return {"type": "chat", "message": "hi", "session_id": "s-1"}
        await asyncio.sleep(0.05)
        raise WebSocketDisconnect()

    ws.receive_json = receive_json_side_effect

    with patch("hypergolic.websocket.router.handle_connect", side_effect=fake_handle_connect):
        with patch("hypergolic.websocket.router.cancel_child_dispatches"):
            await websocket_endpoint(ws)

    assert any(
        call.args[0] == {"type": "t"}
        for call in ws.send_json.call_args_list
    )


@patch("hypergolic.websocket.router.run_session_turn", new_callable=AsyncMock)
async def test_start_turn_runs_process_owned(mock_run, _fresh_globals):
    """start_turn needs no live connection: turns are process-owned tasks."""
    _, tm = _fresh_globals

    router_mod.start_turn("child-1", {"role": "user", "content": [{"type": "text", "text": "hi"}]})
    assert "child-1" in tm.session_tasks
    await tm.session_tasks["child-1"]
    mock_run.assert_called_once()


@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_disconnect_leaves_turns_running(mock_verify, _fresh_globals):
    """A socket disconnect detaches the client but cancels nothing."""
    _, tm = _fresh_globals
    started = asyncio.Event()
    finished = asyncio.Event()

    async def turn(cancel_event: asyncio.Event) -> None:
        started.set()
        await asyncio.sleep(0.05)
        finished.set()

    tm.start_turn("s-live", turn)
    await started.wait()

    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}
    ws.receive_json.side_effect = WebSocketDisconnect()
    await websocket_endpoint(ws)

    task = tm.session_tasks.get("s-live")
    assert task is not None and not task.cancelled()
    await asyncio.wait_for(finished.wait(), timeout=1)


@patch("hypergolic.websocket.router.verify_token", return_value=True)
async def test_reconnect_resends_pending_approval_cards(mock_verify, _fresh_globals):
    _, tm = _fresh_globals
    payload = {"type": "tool_approval_request", "tool_use_id": "tu-9", "session_id": "s-1"}
    tm.approval_payloads["tu-9"] = payload

    ws = AsyncMock()
    ws.cookies = {"h_token": "ok"}
    ws.receive_json.side_effect = WebSocketDisconnect()
    await websocket_endpoint(ws)

    assert any(call.args[0] == payload for call in ws.send_json.call_args_list)


@patch("hypergolic.websocket.router.readonly_session", return_value="s1")
@patch("hypergolic.websocket.router.verify_token", return_value=False)
async def test_spectator_drops_inbound_and_skips_resume(mock_full, mock_ro, _fresh_globals):
    ws = AsyncMock()
    ws.cookies = {"h_token": "ro"}
    ws.receive_json.side_effect = [
        {"type": "approval_response", "approval_id": "a1", "response": {"behavior": "allow"}},
        WebSocketDisconnect(),
    ]

    with patch.object(router_mod, "resolve_approval_response") as resolve:
        await websocket_endpoint(ws)

    ws.accept.assert_called_once()
    resolve.assert_not_called()
    cast(AsyncMock, router_mod.resume_interrupted_sessions).assert_not_awaited()


async def test_scoped_sender_forwards_only_its_session():
    """A spectator token is scoped to one session; everything else — other
    sessions' events and session-less control events — is dropped."""
    ws = AsyncMock()
    sender = router_mod._SessionScopedSender(ws, "s1")
    await sender.send_json({"type": "tool_output_chunk", "session_id": "s1"})
    await sender.send_json({"type": "tool_output_chunk", "session_id": "s2"})
    await sender.send_json({"type": "error"})
    ws.send_json.assert_awaited_once_with({"type": "tool_output_chunk", "session_id": "s1"})
