import asyncio
import logging
from datetime import datetime, timezone

from fastapi import WebSocket

from hypergolic.sessions import session_rows
from hypergolic.dispatch.conclude import (
    BranchPreservationError,
    teardown_worktree_at_conclude,
)
from hypergolic.dispatch.child_end import end_children
from hypergolic.dispatch.lifecycle import cancel_child_dispatches
from hypergolic.dispatch.state import DispatchResult, resolve_dispatch
from hypergolic.dispatch.knowledge import maybe_dispatch_distillation, should_distill
from hypergolic.enums import SessionStatus
from hypergolic.pins.runtime import release_harness_snapshots
from hypergolic.sandbox.manager.lifecycle import schedule_session_sandbox_cleanup
from hypergolic.messages.types import BroadcastEvent, BroadcastFn
from hypergolic.sessions.operations import load_session
from hypergolic.telemetry.events import emit
from hypergolic.websocket.schemas import ConcludeSessionMessage
from hypergolic.websocket.turn_manager import TurnManager

logger = logging.getLogger(__name__)


async def _is_already_concluding(session_id: str) -> bool:
    row = await session_rows.afetch(session_id)
    return row is not None and row.status == SessionStatus.CONCLUDING.value


async def _load_session_or_none(session_id: str):
    try:
        return await asyncio.to_thread(load_session, session_id)
    except Exception:
        return None


async def _send_conclude_error(ws: WebSocket, session_id: str, detail: str) -> None:
    await ws.send_json({
        "type": "conclude_error",
        "session_id": session_id,
        "detail": detail,
    })


async def _teardown_own_worktree(
    msg: ConcludeSessionMessage, ws: WebSocket, session_obj
) -> bool:
    try:
        await teardown_worktree_at_conclude(
            session_obj,
            delete_worktree=msg.delete_worktree,
            delete_branch_flag=msg.delete_branch,
        )
    except BranchPreservationError as err:
        await _send_conclude_error(
            ws,
            msg.session_id,
            "Cannot conclude: the session's branch could not be "
            f"preserved out of its sandbox ({err}). Retry, or conclude "
            "with the branch deleted.",
        )
        return False
    return True


async def _write_conclusion(
    msg: ConcludeSessionMessage, status: SessionStatus, concluded_at: datetime | None
) -> None:
    await session_rows.aupdate(
        msg.session_id,
        conclusion_rating=msg.rating,
        conclusion_feedback=msg.feedback,
        concluded_at=concluded_at,
        status=status.value,
    )


async def _finish_conclusion(
    msg: ConcludeSessionMessage,
    ws: WebSocket,
    broadcast: BroadcastFn,
    session_obj,
    will_distill: bool,
) -> None:
    session_id = msg.session_id
    status = SessionStatus.CONCLUDING if will_distill else SessionStatus.CONCLUDED
    concluded_at = None if will_distill else datetime.now(timezone.utc)
    await _write_conclusion(msg, status, concluded_at)
    await broadcast(BroadcastEvent(
        type="session_status_change",
        role="system",
        content=[{"status": status.value}],
        session_id=session_id,
    ))
    await asyncio.to_thread(release_harness_snapshots, session_id)
    if will_distill:
        asyncio.get_running_loop().create_task(
            maybe_dispatch_distillation(session_obj, broadcast)
        )
    else:
        schedule_session_sandbox_cleanup(session_id)
    await ws.send_json({
        "type": "session_concluded",
        "session_id": session_id,
        "status": status.value,
        "conclusion_rating": msg.rating,
        "conclusion_feedback": msg.feedback,
        "concluded_at": concluded_at.isoformat() if concluded_at else None,
    })


async def handle_conclude_session(
    msg: ConcludeSessionMessage,
    ws: WebSocket,
    tm: TurnManager,
    broadcast: BroadcastFn,
) -> None:
    session_id = msg.session_id
    if await _is_already_concluding(session_id):
        return
    await tm.cancel_existing_turn(session_id)
    await cancel_child_dispatches(session_id)
    session_obj = await _load_session_or_none(session_id)
    if session_obj and not await _teardown_own_worktree(msg, ws, session_obj):
        return
    resolve_dispatch(session_id, DispatchResult(
        outcome="success",
        conclusion="Session was concluded by the user.",
    ))
    await end_children(session_id, broadcast, tm.cancel_existing_turn)
    will_distill = bool(
        msg.analyze_learnings
        and session_obj is not None
        and await should_distill(session_obj)
    )
    emit(
        "session.concluded", session_id=session_id, rating=msg.rating,
        feedback=bool(msg.feedback), distill=will_distill,
    )
    await _finish_conclusion(msg, ws, broadcast, session_obj, will_distill)
