import asyncio
import logging
from dataclasses import dataclass
from typing import Any


from hypergolic.artifacts import artifact_rows
from hypergolic.workflows import workflow_rows
from hypergolic.db.models import DBArtifact
from hypergolic.messages.truncation import mark_messages_truncated
from hypergolic.messages.types import BroadcastEvent, BroadcastFn
from hypergolic.schemas import Session
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.workflows.resolver import get_workflow, get_session_workflow
from hypergolic.workflows.artifact_injection import inject_artifacts_as_user_message

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    pass


@dataclass
class _PendingContextAction:
    truncate_on_entry: bool
    include_artifacts: list[str]


_pending_context_actions: dict[str, list[_PendingContextAction]] = {}


async def activate_workflow(
    session: Session,
    workflow_id: str,
    broadcast: BroadcastFn,
) -> None:
    wf = get_workflow(workflow_id)
    if wf is None:
        raise WorkflowError(f"Workflow '{workflow_id}' not found")

    existing = await asyncio.to_thread(get_session_workflow, session.id)
    if existing is not None:
        raise WorkflowError(
            f"Session already has active workflow '{existing[0]}'. "
            "Deactivate it first."
        )

    initial_state = None
    for s in wf.states:
        if s.id == wf.initial_state:
            initial_state = s
            break
    if initial_state is None:
        raise WorkflowError(
            f"Initial state '{wf.initial_state}' not found in workflow '{workflow_id}'"
        )

    await workflow_rows.start(session.id, workflow_id, initial_state.id)

    await broadcast(BroadcastEvent(
        type="workflow_state_change",
        role="system",
        content=[{
            "workflow_id": workflow_id,
            "workflow_name": wf.name,
            "workflow_state_id": initial_state.id,
            "workflow_state_name": initial_state.name,
        }],
        session_id=session.id,
    ))


def _find_by_id(items, item_id: str):
    return next((item for item in items if item.id == item_id), None)


async def _broadcast_state(
    broadcast: BroadcastFn | None,
    session_id: str,
    workflow_id: str | None,
    workflow_name: str | None,
    state_id: str | None,
    state_name: str | None,
) -> None:
    if not broadcast:
        return
    await broadcast(BroadcastEvent(
        type="workflow_state_change",
        role="system",
        content=[{
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "workflow_state_id": state_id,
            "workflow_state_name": state_name,
        }],
        session_id=session_id,
    ))


async def _store_artifact(
    session: Session,
    workflow_id: str,
    from_state_id: str,
    outcome: str,
    artifact_id: str,
    output: dict[str, Any],
) -> None:
    await artifact_rows.add(DBArtifact(
        session_id=session.id,
        workflow_id=workflow_id,
        state_id=from_state_id,
        outcome=outcome,
        artifact_id=artifact_id,
        content=output,
    ))


async def _complete_workflow(
    session: Session, wf, broadcast: BroadcastFn | None
) -> ToolResult:
    await deactivate_workflow(session.id)
    await _broadcast_state(broadcast, session.id, None, None, None, None)
    return ToolResult.text(
        f"Workflow '{wf.name}' ({wf.id}) completed. Session returned to freeform mode.",
        meta={"workflow_id": wf.id, "workflow_name": wf.name},
    )


def _enqueue_context_action(session_id: str, next_state) -> None:
    if next_state.truncate_on_entry or next_state.include_artifacts:
        _pending_context_actions.setdefault(session_id, []).append(
            _PendingContextAction(
                truncate_on_entry=next_state.truncate_on_entry,
                include_artifacts=list(next_state.include_artifacts),
            )
        )


async def _advance_to_state(
    session: Session, wf, next_state, broadcast: BroadcastFn | None
) -> ToolResult:
    await workflow_rows.move(session.id, next_state.id)
    await _broadcast_state(
        broadcast, session.id, wf.id, wf.name, next_state.id, next_state.name,
    )
    if broadcast is not None:
        _enqueue_context_action(session.id, next_state)
    result_text = f"Transitioned to state '{next_state.name}' ({next_state.id})."
    if next_state.truncate_on_entry:
        result_text += " Prior conversation has been truncated; proceed from the injected artifacts."
    return ToolResult.text(
        result_text,
        meta={
            "workflow_id": wf.id,
            "workflow_name": wf.name,
            "workflow_state_id": next_state.id,
            "workflow_state_name": next_state.name,
        },
    )


async def handle_workflow_transition(
    session: Session,
    workflow_id: str,
    from_state_id: str,
    outcome: str,
    output: dict[str, Any],
    broadcast: BroadcastFn | None = None,
) -> ToolResult:
    wf = get_workflow(workflow_id)
    if wf is None:
        return ToolResult.text(f"Workflow '{workflow_id}' not found", is_error=True)

    from_state = _find_by_id(wf.states, from_state_id)
    if from_state is None:
        return ToolResult.text(f"State '{from_state_id}' not found", is_error=True)

    output_schema = next(
        (o for o in from_state.output_schemas if o.outcome == outcome), None,
    )
    if output_schema is None:
        return ToolResult.text(
            f"Outcome '{outcome}' not defined for state '{from_state_id}'",
            is_error=True,
        )

    if output_schema.artifact_id:
        await _store_artifact(
            session, workflow_id, from_state_id, outcome,
            output_schema.artifact_id, output,
        )

    next_state_id = output_schema.next_state
    if next_state_id is None:
        return await _complete_workflow(session, wf, broadcast)

    next_state = _find_by_id(wf.states, next_state_id)
    if next_state is None:
        return ToolResult.text(
            f"Next state '{next_state_id}' not found in workflow",
            is_error=True,
        )
    return await _advance_to_state(session, wf, next_state, broadcast)


async def deactivate_workflow(session_id: str) -> None:
    await workflow_rows.end(session_id)


async def apply_pending_context_actions(
    session: Session,
    broadcast: BroadcastFn,
) -> None:
    pending = _pending_context_actions.pop(session.id, [])
    for action in pending:
        await _apply_state_entry_context(
            session,
            action.truncate_on_entry,
            action.include_artifacts,
            broadcast,
        )


def discard_pending_context_actions(session_id: str) -> None:
    _pending_context_actions.pop(session_id, None)


async def _apply_state_entry_context(
    session: Session,
    truncate_on_entry: bool,
    artifact_ids: list[str],
    broadcast: BroadcastFn,
) -> None:
    did_truncate = False
    if truncate_on_entry:
        await asyncio.to_thread(mark_messages_truncated, session.id)
        did_truncate = True

    injected = await inject_artifacts_as_user_message(session, artifact_ids, broadcast)

    if did_truncate and not injected:
        await broadcast(BroadcastEvent(
            type="truncated",
            role="system",
            content=[],
            session_id=session.id,
        ))
