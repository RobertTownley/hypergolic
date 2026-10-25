"""Transport-agnostic single-turn runner.

The websocket layer wires ``notify`` to ``ws.send_json``; headless callers
(``hypergolic run``) pass a collector. Everything else — streaming, approvals,
status transitions — already flows through ``broadcast``/``approval_callback``.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any, Awaitable, Callable

from anthropic.types import Message, MessageParam

from hypergolic.commands import approval_bus
from hypergolic.pins.restore import restore_overridden_app
from hypergolic.pins.runtime import pinned_app
from hypergolic.harness.app.state import app_context
from hypergolic.dispatch.lifecycle import fail_dispatch_if_child
from hypergolic.enums import SessionStatus
from hypergolic.git.status import get_git_status
from hypergolic.messages.conversation.loop import create_message
from hypergolic.messages.types import BroadcastFn, UserInterrupt
from hypergolic.schemas import Session
from hypergolic.sessions.errors import format_error_detail, persist_error, persist_error_message
from hypergolic.sessions.operations import load_session
from hypergolic.sessions.repo_resolver import resolve_repo_and_base
from hypergolic.sessions.status import finalize_turn, set_session_status_and_broadcast
from hypergolic.telemetry.log_context import log_context
from hypergolic.telemetry.session_trace import session_link
from hypergolic.telemetry.tracing import root_span
from hypergolic.tools.handlers import ApprovalCallback

logger = logging.getLogger(__name__)

NotifyFn = Callable[[dict[str, Any]], Awaitable[None]]


async def run_session_turn(
    session_id: str,
    message: MessageParam | None,
    cancel_event: asyncio.Event,
    notify: NotifyFn,
    broadcast: BroadcastFn,
    approval_callback: ApprovalCallback,
) -> Message | None:
    """Execute a single conversation turn. Returns the final assistant
    message, or None if the turn was interrupted or errored (the error is
    persisted and delivered via ``notify``, never raised).

    A session with a pinned harness runs its whole turn under that App;
    everything downstream of ``get_app()`` — prompt build, tools, skills,
    approval policies — resolves against the pinned config.
    """
    app = pinned_app(session_id) or await asyncio.to_thread(restore_overridden_app, session_id)
    with root_span(
        "turn", links=[session_link(session_id)], **{"session.id": session_id}
    ), log_context(**{"session.id": session_id}):
        if app is None:
            return await _run_turn(
                session_id, message, cancel_event, notify, broadcast,
                approval_callback,
            )
        with app_context(app):
            return await _run_turn(
                session_id, message, cancel_event, notify, broadcast,
                approval_callback,
            )


async def _run_turn(
    session_id: str,
    message: MessageParam | None,
    cancel_event: asyncio.Event,
    notify: NotifyFn,
    broadcast: BroadcastFn,
    approval_callback: ApprovalCallback,
) -> Message | None:
    try:
        # Inside the try: a resumed or dispatched turn has no caller to hear
        # a load failure, so it belongs in the transcript like any other.
        session: Session = await asyncio.to_thread(load_session, session_id)

        # A broker invocation arrives on an HTTP request part-way through an exec
        # the tool loop is already awaiting, so it needs this turn's approval
        # callback from outside that loop. The window is exactly one turn:
        # outside it there is no human to ask, and the broker refuses rather
        # than hanging.
        approval_bus.register(session_id, approval_callback, broadcast)

        response = await create_message(
            session=session,
            message=message,
            broadcast=broadcast,
            cancel_event=cancel_event,
            approval_callback=approval_callback,
        )

        await finalize_turn(session_id, broadcast)
        done_payload: dict[str, Any] = {"type": "done", "session_id": session_id}
        try:
            # Resolve repo + base rev exactly like the /api/git/status
            # endpoint (origin/<base> in a live clone): a status computed
            # against the local base name would diff HEAD against itself
            # and wipe the UI's "All changes" list at every turn end.
            repo, base_rev = await asyncio.to_thread(
                resolve_repo_and_base, session_id
            )
            git_status = await asyncio.to_thread(
                get_git_status,
                repo=repo,
                session_id=session_id,
                base_branch=base_rev,
            )
            done_payload["git_status"] = git_status.model_dump()
        except Exception:
            logger.debug("Failed to include git_status in done event", exc_info=True)
        await notify(done_payload)
        return response
    except asyncio.CancelledError:
        # A hard cancel (interrupt escalation or process shutdown) must not
        # strand the session in an in-flight status — stale statuses get
        # flagged for resume at the next restart and resurrect dead work.
        with suppress(Exception):
            await asyncio.shield(finalize_turn(session_id, broadcast))
        raise
    except UserInterrupt as ui:
        await set_session_status_and_broadcast(session_id, SessionStatus.IDLE, broadcast)
        try:
            payload: dict[str, Any] = {"type": "interrupted", "session_id": session_id}
            if ui.partial_text:
                payload["partial_text"] = ui.partial_text
            await notify(payload)
        except Exception:
            logger.warning("Failed to deliver interrupt payload", exc_info=True)
        return None
    except Exception as exc:
        logger.error("Error during session turn %s", session_id, exc_info=True)
        detail = format_error_detail(exc)
        await set_session_status_and_broadcast(session_id, SessionStatus.ERROR, broadcast)
        await asyncio.to_thread(persist_error_message, session_id, detail)
        await asyncio.to_thread(persist_error, session_id, exc)
        fail_dispatch_if_child(session_id, detail, broadcast)
        try:
            await notify({"type": "error", "detail": detail, "session_id": session_id})
        except Exception:
            logger.warning("Failed to deliver error payload", exc_info=True)
        return None
    finally:
        approval_bus.unregister(session_id)
