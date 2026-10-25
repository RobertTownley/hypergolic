"""Lifecycle hooks: auto-conclude, fail, cancel, sandbox cleanup."""
from __future__ import annotations

import asyncio
import logging
from anthropic.types import Message, TextBlock

from hypergolic.git.harness_repo import remove_session_workspaces
from hypergolic.dispatch.conclude import (
    BranchPreservationError,
    set_concluded_at,
    teardown_worktree_at_conclude,
)
from hypergolic.dispatch.state import (
    DispatchResult,
    _child_to_parent,
    _finalize_on_auto_conclude,
    _pending_dispatches,
    resolve_dispatch,
)
from hypergolic.enums import SessionStatus
from hypergolic.messages.types import BroadcastEvent, BroadcastFn
from hypergolic.git.worktree_lifecycle import schedule_teardown
from hypergolic.sandbox.manager.lifecycle import schedule_session_sandbox_cleanup
from hypergolic.sessions.operations import clear_session_worktree_fields, load_conducted_by, load_session
from hypergolic.sessions.status import set_session_status, set_session_status_and_broadcast

logger = logging.getLogger(__name__)


def _extract_final_text(response: Message) -> str:
    parts = []
    for block in response.content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
    return "\n".join(parts) if parts else "<no text content>"


async def auto_conclude_if_needed(
    session_id: str,
    parent_id: str | None,
    response: Message,
    broadcast: BroadcastFn,
) -> bool:
    """Resolve a pending dispatch when the child ended its turn without conclude.

    send_turn children stay live (interactive drivers treat this as "agent is
    awaiting the next user message"). dispatch() children are finalized with
    the full conclude lifecycle — status, worktree, sandboxes — so they don't
    linger as open sessions.
    """
    if not parent_id:
        return False
    future = _pending_dispatches.get(session_id)
    if not future or future.done():
        return False

    final_text = _extract_final_text(response)
    conclusion = (
        f"Child session ({session_id}) ended its turn without calling conclude. "
        f"Final message content:\n{final_text}"
    )
    logger.warning("Auto-concluding child session %s (parent: %s)", session_id, parent_id)

    finalize = session_id in _finalize_on_auto_conclude
    surviving_branch = (
        await _teardown_for_auto_conclude(session_id) if finalize else None
    )

    resolved = resolve_dispatch(
        session_id,
        DispatchResult(
            outcome="success",
            conclusion=conclusion,
            auto_concluded=True,
            reply_text=final_text,
            worktree_branch=surviving_branch,
        ),
    )
    if not resolved or not finalize:
        return resolved

    await set_session_status_and_broadcast(session_id, SessionStatus.CONCLUDED, broadcast)
    await asyncio.to_thread(set_concluded_at, session_id)
    schedule_session_sandbox_cleanup(session_id)
    await broadcast(BroadcastEvent(
        type="dispatch_concluded",
        role="system",
        content=[],
        session_id=session_id,
    ))
    return True


async def _teardown_for_auto_conclude(session_id: str) -> str | None:
    """Worktree teardown for a finalized auto-conclude; returns surviving branch.

    Unlike the conclude tool, there is no agent to bounce a preservation
    error back to — so it is logged instead of blocking. Never raises.
    """
    try:
        session = await asyncio.to_thread(load_session, session_id)
    except Exception:
        logger.warning(
            "Could not load session %s for auto-conclude teardown",
            session_id, exc_info=True,
        )
        return None

    try:
        try:
            return await teardown_worktree_at_conclude(
                session, delete_worktree=True, delete_branch_flag=False,
            )
        except BranchPreservationError:
            # No agent to bounce to; the branch is NOT preserved — don't
            # claim survival. Session history remains the recovery path.
            logger.error(
                "Could not preserve session branch during auto-conclude of %s; "
                "its committed work survives only in session history",
                session_id, exc_info=True,
            )
            return None
    except Exception:
        logger.warning(
            "Worktree teardown failed during auto-conclude of %s",
            session_id, exc_info=True,
        )
        return session.worktree_branch
    finally:
        await asyncio.to_thread(remove_session_workspaces, session_id)


def fail_dispatch_if_child(session_id: str, error_detail: str, broadcast: BroadcastFn) -> bool:
    """Fail the parent's dispatch of *session_id*, then end the child the way
    ``dispatch --conclude`` does (worktree, host refs, unused pin branch),
    keeping its ERROR status. A conducted child stays live for ``dispatch --reply``."""
    from hypergolic.dispatch.child_end import end_child  # cycle

    parent_id = _child_to_parent.get(session_id)
    if not parent_id:
        return False
    conclusion = f"Child session ({session_id}) failed with error: {error_detail}"
    logger.warning("Failing child dispatch %s (parent: %s): %s", session_id, parent_id, error_detail)
    resolved = resolve_dispatch(session_id, DispatchResult(outcome="failure", conclusion=conclusion))
    if load_conducted_by(session_id) is not None:
        return resolved
    task = asyncio.get_running_loop().create_task(
        end_child(session_id, broadcast, status=SessionStatus.ERROR),
    )
    _cleanup_tasks.add(task)
    task.add_done_callback(_cleanup_tasks.discard)
    return resolved


_cleanup_tasks: set[asyncio.Task] = set()


async def cancel_child_dispatches(parent_session_id: str) -> None:
    children_to_cancel = [
        child_id for child_id, parent_id in _child_to_parent.items()
        if parent_id == parent_session_id
    ]
    for child_id in children_to_cancel:
        future = _pending_dispatches.pop(child_id, None)
        if future and not future.done():
            future.set_result(DispatchResult(outcome="suppressed", conclusion="Parent session was interrupted"))
        _child_to_parent.pop(child_id, None)
        await asyncio.to_thread(set_session_status, child_id, SessionStatus.INTERRUPTED)
        try:
            await _teardown_child_worktree(child_id)
        except Exception:
            logger.warning(
                "Unexpected error tearing down worktree for child %s",
                child_id, exc_info=True,
            )
        schedule_session_sandbox_cleanup(child_id)
        logger.info("Interrupted child session %s (parent: %s)", child_id, parent_session_id)


async def _teardown_child_worktree(child_session_id: str) -> None:
    """Force-remove a child session's worktree + branch on parent interrupt."""
    try:
        session = await asyncio.to_thread(load_session, child_session_id)
    except Exception:
        logger.warning(
            "Could not load child session %s for worktree teardown",
            child_session_id, exc_info=True,
        )
        return

    try:
        await asyncio.to_thread(
            clear_session_worktree_fields, child_session_id, clear_branch=True
        )
    except Exception:
        logger.warning(
            "Failed to clear worktree fields for child %s",
            child_session_id, exc_info=True,
        )

    try:
        from hypergolic.dispatch.child_end import drop_child_refs  # cycle: child_end -> conclude

        await asyncio.to_thread(drop_child_refs, session, keep_branch=False)
        schedule_teardown(
            session_id=child_session_id, worktree_path=session.worktree_path,
        )
    except Exception:
        logger.warning(
            "Worktree teardown scheduling failed for interrupted child %s",
            child_session_id, exc_info=True,
        )


