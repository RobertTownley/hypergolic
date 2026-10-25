"""Kick sessions a restart interrupted back into motion on a fresh connection.

A turn needs a live WebSocket — it streams, and it may need approval — so this
runs on connect, before the receive loop, reusing the turn runner dispatch uses.
"""
from __future__ import annotations

import asyncio
import logging

from hypergolic.dispatch.state import TurnRunnerFn
from hypergolic.sessions.resume import claim_resumable_sessions, set_session_resume

logger = logging.getLogger(__name__)


async def resume_interrupted_sessions(start_turn: TurnRunnerFn) -> None:
    try:
        session_ids = await asyncio.to_thread(claim_resumable_sessions)
    except Exception:
        logger.error("Failed to claim sessions for post-restart resume", exc_info=True)
        return

    # Re-flagging is a plain (fast) DB write rather than a thread hop: it has
    # to work while the connection is being cancelled.
    for index, session_id in enumerate(session_ids):
        logger.info("Resuming session %s after server restart", session_id)
        try:
            start_turn(session_id, None)
        except asyncio.CancelledError:
            for unstarted in session_ids[index:]:
                set_session_resume(unstarted, True)
            raise
        except Exception:
            logger.error("Failed to resume session %s; re-flagging", session_id, exc_info=True)
            set_session_resume(session_id, True)
