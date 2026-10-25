import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from hypergolic.sessions import session_rows
from hypergolic.dispatch.conclude.errors import BranchPreservationError
from hypergolic.dispatch.conclude.worktree import teardown_worktree_at_conclude
from hypergolic.dispatch.state import DispatchResult, resolve_dispatch
from hypergolic.enums import SessionStatus
from hypergolic.git.harness_repo import remove_session_workspaces
from hypergolic.mcptools.sessions import clear_enabled_servers
from hypergolic.messages.types import BroadcastEvent
from hypergolic.pins.runtime import release_harness_snapshots
from hypergolic.sandbox.manager.lifecycle import schedule_session_sandbox_cleanup
from hypergolic.sessions.status import set_session_status_and_broadcast
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.commands.argv import positional

logger = logging.getLogger(__name__)

class ConcludeInput(BaseModel):
    outcome: Literal["success", "failure", "suppressed"]
    conclusion: str
    merge_ready: bool = Field(
        default=False,
        description=(
            "Advisory to the parent (worktree sessions); authorizes nothing"
        ),
    )
    delete_worktree: bool = Field(
        default=True,
        description=(
            "False keeps the checkout for the user. Uncommitted "
            "changes are never preserved; the parent sees only commits"
        ),
    )


def set_concluded_at(session_id: str) -> datetime:
    concluded_at = datetime.now(timezone.utc)
    session_rows.update(session_id, concluded_at=concluded_at)
    clear_enabled_servers(session_id)
    return concluded_at

async def _end_own_children(session, ctx: ToolContext) -> None:
    from hypergolic.dispatch.child_end import drop_child_refs, end_children

    await end_children(session.id, ctx.broadcast)
    if session.parent_id:
        await asyncio.to_thread(drop_child_refs, session, keep_branch=True)


async def _handle_conclude(inp: ConcludeInput, ctx: ToolContext) -> ToolResult:
    session = ctx.session

    surviving_branch: str | None = None
    try:
        surviving_branch = await teardown_worktree_at_conclude(
            session,
            delete_worktree=inp.delete_worktree,
            delete_branch_flag=False,
        )
    except BranchPreservationError as err:
        return ToolResult.text(
            "Cannot conclude: your work could not be preserved out of the "
            f"sandbox ({err}). Retry once; if it persists, report the error "
            "in your final message instead of concluding.",
            is_error=True,
        )

    await asyncio.to_thread(remove_session_workspaces, session.id)
    await _end_own_children(session, ctx)

    result = DispatchResult(
        outcome=inp.outcome,
        conclusion=inp.conclusion,
        merge_ready=inp.merge_ready,
        worktree_branch=surviving_branch,
    )
    resolved = resolve_dispatch(session.id, result)

    if not resolved:
        parent_id = session.parent_id
        if parent_id:
            await set_session_status_and_broadcast(
                session.id, SessionStatus.CONCLUDED, ctx.broadcast,
            )
            await asyncio.to_thread(set_concluded_at, session.id)
            schedule_session_sandbox_cleanup(session.id)
            await asyncio.to_thread(release_harness_snapshots, session.id)
            return ToolResult.text(f"Session concluded with outcome: {inp.outcome}")
        return ToolResult.text("No pending dispatch to conclude.", is_error=True)

    await set_session_status_and_broadcast(
        session.id, SessionStatus.CONCLUDED, ctx.broadcast,
    )
    await asyncio.to_thread(set_concluded_at, session.id)

    schedule_session_sandbox_cleanup(session.id)
    await asyncio.to_thread(release_harness_snapshots, session.id)

    parent_id = session.parent_id
    if parent_id:
        await ctx.broadcast(BroadcastEvent(
            type="dispatch_concluded",
            role="system",
            content=[],
            session_id=session.id,
        ))

    return ToolResult.text(f"Session concluded with outcome: {inp.outcome}")


ConcludeTool = Tool(
    id="conclude",
    tags=["finish", "wrap-up", "handoff", "outcome"],
    name="conclude",
    description="End this session, returning the conclusion to the parent ('suppressed' = cancel)",
    input_schema=ConcludeInput,
    argv=positional(
        "outcome",
        joined="conclusion",
        bools={"merge_ready"},
        negated={"keep_worktree"},
        remap={"keep_worktree": "delete_worktree"},
    ),
    usage=(
        "conclude <success|failure|suppressed> <conclusion...> "
        "[--merge-ready] [--keep-worktree]"
    ),
    run=_handle_conclude,
)
