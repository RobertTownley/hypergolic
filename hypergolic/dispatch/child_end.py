from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable


from hypergolic.sessions import session_rows
from hypergolic.dispatch.conclude import set_concluded_at, teardown_worktree_at_conclude
from hypergolic.dispatch.state import (
    _child_to_parent,
    _finalize_on_auto_conclude,
    _pending_dispatches,
)
from hypergolic.enums import SessionStatus
from hypergolic.harness.app.state import get_app
from hypergolic.git.parent_land import PARENT_PIN_PREFIX, drop_parent_pin
from hypergolic.git.sandbox_repo import delete_hypergolic_ref
from hypergolic.git.worktree_lifecycle import schedule_teardown
from hypergolic.messages.types import BroadcastEvent, BroadcastFn
from hypergolic.pins.runtime import release_harness_snapshots
from hypergolic.sandbox.manager.lifecycle import schedule_session_sandbox_cleanup
from hypergolic.schemas import Session
from hypergolic.sessions.operations import clear_session_worktree_fields, load_session
from hypergolic.sessions.status import set_session_status_and_broadcast
from hypergolic.tools import approval_delegate

logger = logging.getLogger(__name__)

CancelTurnFn = Callable[[str], Awaitable[None]]

_ENDED = (SessionStatus.CONCLUDED.value, SessionStatus.INTERRUPTED.value)


def forget_child(child_id: str) -> None:
    _pending_dispatches.pop(child_id, None)
    _child_to_parent.pop(child_id, None)
    _finalize_on_auto_conclude.discard(child_id)
    approval_delegate.close(child_id)


def child_ref_branches(child: Session, *, keep_branch: bool) -> list[str]:
    branches: list[str] = []
    if child.worktree_branch and not keep_branch:
        branches.append(child.worktree_branch)
    if child.base_branch and child.base_branch.startswith(PARENT_PIN_PREFIX):
        branches.append(child.base_branch)
    return branches


def drop_child_refs(child: Session, *, keep_branch: bool) -> None:
    for branch in child_ref_branches(child, keep_branch=keep_branch):
        try:
            delete_hypergolic_ref(child.project_path, child.project_id, branch)
        except Exception:
            logger.warning("Could not delete ref of %s for child %s", branch, child.id, exc_info=True)


async def _drop_unused_pin(child: Session) -> None:
    pin_sha = child.repo_pins.get("app")
    if not (child.parent_id and pin_sha and child.base_branch and child.base_branch.startswith(PARENT_PIN_PREFIX)):
        return
    try:
        parent = await asyncio.to_thread(load_session, child.parent_id)
        project = get_app().find_project(child.project_id)
    except Exception:
        return
    if project is not None:
        await drop_parent_pin(parent, project, name=child.base_branch, sha=pin_sha)


async def _teardown(child: Session, *, keep_branch: bool) -> None:
    if keep_branch:
        try:
            await teardown_worktree_at_conclude(child, delete_worktree=True, delete_branch_flag=False)
            return
        except Exception:
            logger.warning("Could not preserve the branch of child %s", child.id, exc_info=True)
    await asyncio.to_thread(clear_session_worktree_fields, child.id, clear_branch=True)
    schedule_teardown(session_id=child.id, worktree_path=child.worktree_path)


async def end_child(
    child_id: str, broadcast: BroadcastFn, *, keep_branch: bool = False,
    status: SessionStatus = SessionStatus.CONCLUDED,
) -> None:
    forget_child(child_id)
    try:
        child = await asyncio.to_thread(load_session, child_id)
    except Exception:
        logger.warning("Could not load child %s to end it", child_id, exc_info=True)
        return
    try:
        await _teardown(child, keep_branch=keep_branch)
    except Exception:
        logger.warning("Worktree teardown failed for child %s", child_id, exc_info=True)
    await asyncio.to_thread(drop_child_refs, child, keep_branch=keep_branch)
    await _drop_unused_pin(child)
    await set_session_status_and_broadcast(child_id, status, broadcast)
    await asyncio.to_thread(set_concluded_at, child_id)
    schedule_session_sandbox_cleanup(child_id)
    await asyncio.to_thread(release_harness_snapshots, child_id)
    if status == SessionStatus.CONCLUDED:
        await broadcast(BroadcastEvent(type="dispatch_concluded", role="system", content=[], session_id=child_id))


def _children_of(parent_id: str) -> list[tuple[str, str | None]]:
    return [(row.id, row.status) for row in session_rows.find(parent_id=parent_id)]


async def end_children(
    parent_id: str, broadcast: BroadcastFn, cancel_turn: CancelTurnFn | None = None,
) -> list[str]:
    ended: list[str] = []
    for child_id, status in await asyncio.to_thread(_children_of, parent_id):
        if status in _ENDED:
            try:
                child = await asyncio.to_thread(load_session, child_id)
            except Exception:
                continue
            await asyncio.to_thread(drop_child_refs, child, keep_branch=False)
            continue
        if cancel_turn is not None:
            await cancel_turn(child_id)
        await end_child(child_id, broadcast)
        ended.append(child_id)
    return ended
