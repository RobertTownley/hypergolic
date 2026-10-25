"""Shared dispatch state: the pending-future registry and turn runner."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from anthropic.types import MessageParam


TurnRunnerFn = Callable[[str, MessageParam | None], Any]


@dataclass
class DispatchResult:
    outcome: str  # "success", "failure", "suppressed", "started", "awaiting_approval"
    conclusion: str
    merge_ready: bool = False
    worktree_branch: str | None = None
    child_session_id: str | None = None
    # Set when the child ended its turn without calling conclude (auto-conclude).
    # For dispatch() children the session is finalized (concluded, torn down);
    # for send_turn children it stays live and can take another send_turn.
    auto_concluded: bool = False
    reply_text: str | None = None  # the child's final message text that turn
    conducted: bool = False


_pending_dispatches: dict[str, asyncio.Future[DispatchResult]] = {}
_child_to_parent: dict[str, str] = {}
# Children registered via dispatch() (fire-and-forget): an auto-conclude
# fully finalizes the session. send_turn children stay live instead.
_finalize_on_auto_conclude: set[str] = set()
_turn_runner: TurnRunnerFn | None = None


def register_turn_runner(runner: TurnRunnerFn) -> None:
    global _turn_runner
    _turn_runner = runner


def resolve_dispatch(session_id: str, result: DispatchResult) -> bool:
    """Hand the child's result to its waiting dispatch.

    A child that delegates approvals keeps its entry: its parent may be between
    an early return and ``dispatch --resume``, and the resumed wait must still
    find the result. That wait releases the entry.
    """
    from hypergolic.tools.approval_delegate import inbox_for

    future = _pending_dispatches.get(session_id)
    if future is None or future.done():
        return False
    future.set_result(result)
    if inbox_for(session_id) is None:
        _pending_dispatches.pop(session_id, None)
        _child_to_parent.pop(session_id, None)
        _finalize_on_auto_conclude.discard(session_id)
    return True
