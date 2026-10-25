import asyncio
import os
import sys
import threading

from hypergolic.enums import SessionStatus
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.sessions.resume import set_session_resume
from hypergolic.sessions.status import set_session_status
import time


def _restart_after_delay(session_id: str, delay: float = 1.0) -> None:
    """Replace the current process with a fresh invocation after a delay."""

    time.sleep(delay)
    try:
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except OSError:
        # No restart means no interrupted turn: drop the flag so a later
        # reconnect doesn't resume a session that was never cut off.
        set_session_resume(session_id, False)
        raise


async def run_restart(ctx: ToolContext) -> ToolResult:
    await asyncio.to_thread(set_session_status, ctx.session.id, SessionStatus.IDLE)
    # Flagged before the process dies so the reconnecting client resumes this
    # session even though its status was parked IDLE rather than left in flight.
    await asyncio.to_thread(set_session_resume, ctx.session.id, True)

    thread = threading.Thread(
        target=_restart_after_delay, args=(ctx.session.id,), daemon=True
    )
    thread.start()

    return ToolResult.text(
        "Server restart initiated. The process re-launches in ~1 second "
        "and this session picks up where it left off once the UI "
        "reconnects — no new message needed.",
    )


restart_tool = Tool(
    id="restart",
    tags=["restart", "server", "core", "package-upgrade"],
    name="Restart Server",
    description="Restart the whole server process; interrupts every session. Only needed for changes to the hypergolic package itself — use reload_harness for ~/.hypergolic edits",
    run=run_restart,
    approval=always("REQUIRE_APPROVAL"),
)
