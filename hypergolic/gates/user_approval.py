from __future__ import annotations

import asyncio
import time

from hypergolic.commands import approval_bus
from hypergolic.gates.request import GateVerdict, LandRequest, passed
from hypergolic.harness.primitives.approval import ToolApprovalDecision
from hypergolic.ids import new_id
from hypergolic.tools.approval import ApprovalRequest, session_decision
from hypergolic.tools.approval_outcome import format_denial, record_approval


async def run_user_approval(req: LandRequest) -> GateVerdict:
    """Block on the human in the merge-review takeover, or on the parent.

    The gate's own posture is ``REQUIRE_APPROVAL``; :func:`session_decision`
    turns it into what this session can get, as on every other route
    (except that auto-approve does not skip a merge review). A
    child with a waiting parent delegates (the parent may approve a merge into
    the child's own base branch); a child nobody waits on is refused.
    """
    label = "user approval"
    decision = session_decision(ToolApprovalDecision(decision="REQUIRE_APPROVAL"), req.session)
    # Auto-approve never skips a merge review: ALLOW still asks the human.
    if decision.decision == "DENY":
        return GateVerdict(ok=False, lines=[
            f"✗ {label}: {decision.reason or 'no one can approve this merge'}",
        ])
    channel = approval_bus.channel(req.session.id)
    if channel is None:
        return GateVerdict(ok=False, lines=[
            f"✗ {label}: no human is attached to this session right now",
        ])
    request_id = new_id()
    base = req.slot.base_branch
    request = ApprovalRequest(
        request_id=request_id,
        tool_name="land",
        tool_input={
            "command": f"git push origin HEAD:{base}",
            "invocation": f"git push origin HEAD:{base}",
            "repo": req.slot.repo,
            "commit_message": req.message,
            "description": req.description,
            "arguments": {
                "repo": req.slot.repo, "sha": req.candidate,
                "base_sha": req.base_sha, "branch": base, "message": req.message,
            },
        },
        session_id=req.session.id,
        tool_display_name=f"Merge into {base}",
        delegated=decision.decision == "DELEGATE",
    )
    started = time.monotonic()
    response = await channel.callback(request)
    await asyncio.to_thread(
        record_approval,
        session_id=req.session.id,
        tool_use_id=request_id,
        tool_name="land",
        tool_input=request.tool_input,
        response=response,
    )
    if not response.approved:
        return GateVerdict(ok=False, lines=[f"✗ {label}", format_denial(response)])
    lines = [passed(f"{label}: approved", started)]
    for ann in response.annotations or []:
        where = f" on “{ann.highlighted_text[:60]}”" if ann.highlighted_text else ""
        lines.append(f"note{where}: {ann.comment}")
    return GateVerdict(ok=True, lines=lines)
