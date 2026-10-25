import asyncio
from unittest.mock import AsyncMock

import pytest

from hypergolic.tools.approval_view import ResolvedView
from hypergolic.tools.handlers import ApprovalRequest, ApprovalResponse
from hypergolic.websocket.approval import build_approval_callback, resolve_approval_response
from hypergolic.websocket.schemas import AnnotationPayload, ApprovalResponseMessage
from hypergolic.websocket.turn_manager import TurnManager


async def test_approval_callback_basic(broadcast):
    hub = AsyncMock()
    tm = TurnManager()

    callback = build_approval_callback(hub, tm, broadcast)

    req = ApprovalRequest(
        request_id="tu-1",
        tool_name="write_file",
        tool_input={"path": "/tmp/x"},
        session_id="s-1",
    )

    async def approve_soon():
        await asyncio.sleep(0.01)
        entry = tm.pending_approvals.get("tu-1")
        assert entry is not None
        _, fut = entry
        fut.set_result(ApprovalResponse(approved=True))

    task = asyncio.create_task(approve_soon())
    result = await callback(req)
    await task

    assert result.approved is True
    hub.send.assert_called_once()
    payload = hub.send.call_args[0][0]
    assert payload["type"] == "tool_approval_request"
    assert payload["tool_use_id"] == "tu-1"
    assert broadcast.call_count == 2  # AWAITING_APPROVAL + TOOL_USE


async def test_approval_callback_no_session_id(broadcast):
    hub = AsyncMock()
    tm = TurnManager()

    callback = build_approval_callback(hub, tm, broadcast)

    req = ApprovalRequest(
        request_id="tu-2",
        tool_name="cmd",
        tool_input={},
        session_id=None,
    )

    async def approve_soon():
        await asyncio.sleep(0.01)
        _, fut = tm.pending_approvals["tu-2"]
        fut.set_result(ApprovalResponse(approved=False, denial_reason="no"))

    task = asyncio.create_task(approve_soon())
    result = await callback(req)
    await task

    assert result.approved is False
    broadcast.assert_not_called()


async def test_approval_callback_with_approval_view(broadcast):
    hub = AsyncMock()
    tm = TurnManager()

    callback = build_approval_callback(hub, tm, broadcast)

    view = ResolvedView(blocks=[{
        "type": "code",
        "value": "ls",
        "language": "bash",
        "label": None,
        "max_height": "half",
    }])
    req = ApprovalRequest(
        request_id="tu-3",
        tool_name="cmd",
        tool_input={"command": "ls"},
        session_id="s-1",
        approval_view=view,
        tool_display_name="Shell Command",
    )

    async def approve_soon():
        await asyncio.sleep(0.01)
        _, fut = tm.pending_approvals["tu-3"]
        fut.set_result(ApprovalResponse(approved=True))

    task = asyncio.create_task(approve_soon())
    result = await callback(req)
    await task

    payload = hub.send.call_args[0][0]
    assert payload["tool_display_name"] == "Shell Command"
    assert "approval_view" in payload
    assert payload["approval_view"]["blocks"][0]["value"] == "ls"
    assert payload["approval_view"]["show_raw_json"] is True
    assert result.approved is True


async def test_approval_callback_cleans_up_on_cancel(broadcast):
    hub = AsyncMock()
    tm = TurnManager()

    callback = build_approval_callback(hub, tm, broadcast)

    req = ApprovalRequest(
        request_id="tu-4",
        tool_name="cmd",
        tool_input={},
        session_id="s-1",
    )

    async def cancel_soon():
        await asyncio.sleep(0.01)
        _, fut = tm.pending_approvals["tu-4"]
        fut.cancel()

    task = asyncio.create_task(cancel_soon())
    with pytest.raises(asyncio.CancelledError):
        await callback(req)
    await task
    assert "tu-4" not in tm.pending_approvals
    assert "tu-4" not in tm.approval_payloads


def test_resolve_approval_response_approved():
    tm = TurnManager()
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    tm.pending_approvals["tu-1"] = ("s-1", fut)

    msg = ApprovalResponseMessage(
        tool_use_id="tu-1",
        approved=True,
    )
    resolve_approval_response(msg, tm)
    assert fut.done()
    assert fut.result().approved is True
    loop.close()


def test_resolve_approval_response_denied_with_annotations():
    tm = TurnManager()
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    tm.pending_approvals["tu-2"] = ("s-1", fut)

    msg = ApprovalResponseMessage(
        tool_use_id="tu-2",
        approved=False,
        denial_reason="bad code",
        annotations=[AnnotationPayload(highlighted_text="line 5", comment="fix this")],
    )
    resolve_approval_response(msg, tm)
    result = fut.result()
    assert result.approved is False
    assert result.denial_reason == "bad code"
    assert len(result.annotations) == 1
    assert result.annotations[0].highlighted_text == "line 5"
    loop.close()


def test_resolve_approval_response_no_pending():
    tm = TurnManager()
    msg = ApprovalResponseMessage(tool_use_id="tu-999", approved=True)
    resolve_approval_response(msg, tm)


def test_resolve_approval_response_already_done():
    tm = TurnManager()
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    fut.set_result(ApprovalResponse(approved=True))
    tm.pending_approvals["tu-1"] = ("s-1", fut)

    msg = ApprovalResponseMessage(tool_use_id="tu-1", approved=False)
    resolve_approval_response(msg, tm)
    assert fut.result().approved is True
    loop.close()
