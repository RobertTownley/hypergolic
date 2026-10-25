"""Process-global turn registry.

One manager owns every running turn, keyed by session id, regardless of which
WebSocket started it. Connections attach/detach at the hub; only an explicit
interrupt (new message to the same session, conclude) cancels a turn — a
disconnect never does.
"""
import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Callable

from hypergolic.tools.handlers import ApprovalResponse

logger = logging.getLogger(__name__)

CANCEL_GRACE = 0.5


class TurnManager:
    def __init__(self) -> None:
        self.session_tasks: dict[str, asyncio.Task[Any]] = {}
        self.session_cancel_events: dict[str, asyncio.Event] = {}
        self.pending_approvals: dict[str, tuple[str, asyncio.Future[ApprovalResponse]]] = {}
        # Request payloads for in-flight approvals, re-sent to reconnecting
        # clients so their approval cards survive a page reload.
        self.approval_payloads: dict[str, dict[str, Any]] = {}

    async def cancel_existing_turn(self, target_session_id: str) -> None:
        existing_task = self.session_tasks.get(target_session_id)
        if not existing_task or existing_task.done():
            return

        existing_cancel = self.session_cancel_events.get(target_session_id)
        if existing_cancel:
            existing_cancel.set()

        to_remove = [
            tool_use_id
            for tool_use_id, (sid, fut) in self.pending_approvals.items()
            if sid == target_session_id
        ]
        for tool_use_id in to_remove:
            _, fut = self.pending_approvals.pop(tool_use_id)
            self.approval_payloads.pop(tool_use_id, None)
            if not fut.done():
                fut.cancel()

        try:
            await asyncio.wait_for(existing_task, timeout=CANCEL_GRACE)
        except (asyncio.TimeoutError, Exception):
            existing_task.cancel()
            try:
                await existing_task
            except (asyncio.CancelledError, Exception):
                logger.debug("Previous task cancelled during new turn", exc_info=True)

    def start_turn(
        self,
        target_session_id: str,
        coro: Callable[[asyncio.Event], Coroutine[Any, Any, None]],
    ) -> asyncio.Task[Any]:
        new_cancel_event = asyncio.Event()
        self.session_cancel_events[target_session_id] = new_cancel_event
        task = asyncio.create_task(coro(new_cancel_event))
        self.session_tasks[target_session_id] = task

        def _cleanup_task(t: asyncio.Task[Any], sid: str = target_session_id) -> None:
            if self.session_tasks.get(sid) is t:
                self.session_tasks.pop(sid, None)
                self.session_cancel_events.pop(sid, None)

        task.add_done_callback(_cleanup_task)
        return task


_manager = TurnManager()


def get_turn_manager() -> TurnManager:
    return _manager
