from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path


from anthropic.types import MessageParam

from hypergolic.messages import message_rows
from hypergolic.sessions import session_rows
from hypergolic.enums import SessionStatus
from hypergolic.dispatch import state as dispatch_state
from hypergolic.dispatch.runner import CONCLUDE_INSTRUCTION, _build_child_session_payload
from hypergolic.dispatch.state import (
    DispatchResult,
    _child_to_parent,
    _finalize_on_auto_conclude,
    _pending_dispatches,
)
from hypergolic.git.commands import async_run_git_command
from hypergolic.harness.app.state import get_app
from hypergolic.messages.types import BroadcastEvent, BroadcastFn
from hypergolic.sandbox.manager.lifecycle import schedule_session_sandbox_cleanup
from hypergolic.schemas import Session
from hypergolic.sessions.operations import create_session

logger = logging.getLogger(__name__)

_MIN_ASSISTANT_MESSAGES = 3

_DISTILL_PROMPT = """\
Session {sid} in this project just concluded. Distill its durable learnings \
into the knowledge base.

1. Run `activate_skill knowledge-base` (curation conventions) and \
`activate_skill history` (read-only SQL over Hypergolic's own DB).
2. Explore frugally. User messages carry the most signal (corrections, \
preferences, goals); user-role rows containing 'tool_use_id' are tool \
results — skip them:
   - SELECT sequence, left(content::text, 2000) FROM messages WHERE \
session_id='{sid}' AND role='user' AND content::text NOT LIKE '%tool_use_id%' \
ORDER BY sequence
   - SELECT tool_name, approved, denial_reason, annotations FROM \
tool_approvals WHERE session_id='{sid}' AND (approved=false OR annotations \
IS NOT NULL) — annotations are inline user feedback on artifacts (including \
approved ones); weigh them heavily
   - Drill into other rows only where these point somewhere interesting.
3. Record durable facts under /shared/knowledge/ — succinct, modular, \
discoverable. Curate as you go: supersede stale facts, dedupe, keep touched \
README indexes accurate.
4. Retro the harness itself: would a tool, skill, prompt, or sandbox \
change have made that session materially cheaper, safer, or less frustrating? \
If so, write a proposal to /shared/harness/proposals/<slug>.md — problem, \
evidence (session id), sketch of the change. Update or delete existing \
proposals it supersedes; skip anything already filed.
5. In /shared, commit and `git push origin main`; unpushed work is lost \
when the session ends.
6. Conclude with a one-line summary of what you recorded.

Most sessions yield 0-3 durable facts and no proposals; if nothing qualifies, \
change nothing and conclude. Do not commit or touch files under /app."""


def _assistant_message_count(session_id: str) -> int:
    return sum(m.role == "assistant" for m in message_rows.for_session(session_id))


def _user_rating_block(session_id: str) -> str:
    row = session_rows.fetch(session_id)
    if row is None or row.conclusion_rating is None:
        return ""
    block = f"User Rating: {row.conclusion_rating}/5"
    feedback = (row.conclusion_feedback or "").strip()
    if feedback:
        block += f". Comment: {feedback}"
    return f"\n\n{block}"


async def should_distill(session: Session) -> bool:
    app = get_app()
    if not getattr(app, "knowledge_distillation", True) or session.parent_id:
        return False
    if dispatch_state._turn_runner is None:
        return False
    count = await asyncio.to_thread(_assistant_message_count, session.id)
    return count >= _MIN_ASSISTANT_MESSAGES


async def finalize_deferred_conclude(parent_id: str, broadcast: BroadcastFn) -> None:
    concluded_at = datetime.now(timezone.utc)
    if not await session_rows.atransition(
        parent_id, SessionStatus.CONCLUDING.value, status=SessionStatus.CONCLUDED.value, concluded_at=concluded_at,
    ):
        return
    schedule_session_sandbox_cleanup(parent_id)
    await broadcast(BroadcastEvent(
        type="session_status_change",
        role="system",
        content=[{
            "status": SessionStatus.CONCLUDED.value,
            "concluded_at": concluded_at.isoformat(),
        }],
        session_id=parent_id,
    ))


async def maybe_dispatch_distillation(session: Session, broadcast: BroadcastFn) -> None:
    dispatched = False
    try:
        dispatched = await _dispatch_distillation(session, broadcast)
    except Exception:
        logger.warning(
            "Knowledge distillation failed for session %s", session.id, exc_info=True
        )
    if not dispatched:
        await finalize_deferred_conclude(session.id, broadcast)


async def _dispatch_distillation(session: Session, broadcast: BroadcastFn) -> bool:
    if not await should_distill(session):
        return False
    app = get_app()
    runner = dispatch_state._turn_runner
    assert runner is not None

    project = app.find_project(session.project_id)
    if project is None:
        return False
    base = await async_run_git_command(
        "rev-parse", "--abbrev-ref", "HEAD", cwd=Path(project.path)
    )
    branch = base.stdout.strip()
    base_branch = branch if branch and branch != "HEAD" else "main"

    role = "researcher" if app.get_role("researcher") else "generalist"
    rating = await asyncio.to_thread(_user_rating_block, session.id)
    prompt = _DISTILL_PROMPT.format(sid=session.id) + rating
    child = await asyncio.to_thread(
        lambda: create_session(
            project_id=session.project_id,
            base_branch=base_branch,
            model_tier=session.model_tier,
            role=role,
            parent_id=session.id,
            dispatch_prompt=prompt + CONCLUDE_INSTRUCTION,
        )
    )

    future: asyncio.Future[DispatchResult] = asyncio.get_running_loop().create_future()
    _pending_dispatches[child.id] = future
    _child_to_parent[child.id] = session.id
    _finalize_on_auto_conclude.add(child.id)

    def _on_child_done(fut: asyncio.Future[DispatchResult]) -> None:
        if not fut.cancelled():
            fut.exception()
        asyncio.ensure_future(finalize_deferred_conclude(session.id, broadcast))

    future.add_done_callback(_on_child_done)

    try:
        payload = await asyncio.to_thread(_build_child_session_payload, child.id)
        await broadcast(BroadcastEvent(
            type="dispatch_started",
            role="system",
            content=[{"child_session_id": child.id, "child_session": payload}],
            session_id=session.id,
        ))

        user_message: MessageParam = {
            "role": "user",
            "content": [{
                "type": "text",
                "text": "Distill the concluded session's learnings per your dispatch context.",
            }],
        }
        runner(child.id, user_message)
    except BaseException:
        _pending_dispatches.pop(child.id, None)
        _child_to_parent.pop(child.id, None)
        _finalize_on_auto_conclude.discard(child.id)
        future.remove_done_callback(_on_child_done)
        raise
    logger.info("Dispatched knowledge distillation %s for session %s", child.id, session.id)
    return True
