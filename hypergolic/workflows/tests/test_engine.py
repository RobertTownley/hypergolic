from contextlib import contextmanager
from typing import Any, cast
from unittest.mock import patch

import pytest

from hypergolic.db.models import DBMessage
from hypergolic.harness.primitives.bundles import OutputSchema, Workflow, WorkflowState
from hypergolic.workflows.engine import (
    WorkflowError,
    _pending_context_actions,
    activate_workflow,
    apply_pending_context_actions,
    deactivate_workflow,
    discard_pending_context_actions,
    handle_workflow_transition,
)
from hypergolic.workflows.artifact_injection import load_artifacts
from tests._factories import (
    build_session as _session,
    build_workflow as _workflow,
)
from tests.conftest import make_artifact, make_message, make_project, make_session
from tests.helpers.tables import FakeMessageRows


@pytest.fixture(autouse=True)
def _clear_pending_context_actions():
    _pending_context_actions.clear()
    yield
    _pending_context_actions.clear()


@pytest.fixture(autouse=True)
def _seed():
    make_project("p-1")
    make_session(sid="s-1", project_id="p-1")


@pytest.fixture
def session():
    return _session()


def _messages(message_rows: FakeMessageRows, *, live_only: bool = False) -> list[DBMessage]:
    return [m for m in message_rows.for_session("s-1") if not (live_only and m.truncated)]


@contextmanager
def _patched(wf, *, fresh: bool = False):
    with patch("hypergolic.workflows.engine.get_workflow", return_value=wf):
        if fresh:
            with patch("hypergolic.workflows.engine.get_session_workflow", return_value=None):
                yield
        else:
            yield


@pytest.mark.parametrize(
    "wf, match",
    [
        (None, "not found"),
        (
            Workflow(
                id="wf-1", name="WF", description="d", initial_state="missing-state",
                states=[WorkflowState(id="other-state", name="Other", prompt="p")],
            ),
            "Initial state",
        ),
    ],
)
async def test_activate_workflow_errors(broadcast, session, wf, match):
    with _patched(wf, fresh=True), pytest.raises(WorkflowError, match=match):
        await activate_workflow(session, "wf-1", broadcast)


async def test_activate_workflow_already_active(broadcast, session, workflow_rows):
    workflow_rows.seed("s-1", "wf-existing", "st-x")

    with _patched(_workflow()), pytest.raises(WorkflowError, match="already has active workflow"):
        await activate_workflow(session, "wf-1", broadcast)


async def test_activate_workflow_success(broadcast, session, workflow_rows):
    with _patched(_workflow(), fresh=True):
        await activate_workflow(session, "wf-1", broadcast)

    assert workflow_rows.active("s-1") == ("wf-1", "st-1")

    broadcast.assert_awaited_once()
    assert broadcast.call_args[0][0].type == "workflow_state_change"


@pytest.mark.parametrize(
    "wf, current_state, outcome, error_substring",
    [
        (None, "st-1", "done", "not found"),
        (_workflow(), "st-missing", "done", "not found"),
        (_workflow(outcome="success"), "st-1", "unknown-outcome", "not defined"),
    ],
)
async def test_transition_error_paths(session, wf, current_state, outcome, error_substring):
    with _patched(wf):
        result = await handle_workflow_transition(session, "wf-1", current_state, outcome, {})
    assert result.is_error is True
    assert error_substring in result.first_text()


async def test_transition_to_next_state(broadcast, session, workflow_rows):
    workflow_rows.seed()

    with _patched(_workflow(next_state_id="st-2")):
        result = await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=broadcast
        )
    assert result.is_error is False
    assert "st-2" in result.first_text()

    assert workflow_rows.active("s-1") == ("wf-1", "st-2")

    assert result.meta == {
        "workflow_id": "wf-1",
        "workflow_name": "Workflow wf-1",
        "workflow_state_id": "st-2",
        "workflow_state_name": "State Two",
    }

    broadcast.assert_awaited_once()
    event = broadcast.call_args[0][0]
    assert event.type == "workflow_state_change"
    assert event.content[0]["workflow_state_id"] == "st-2"


async def test_transition_to_completion(broadcast, session, workflow_rows):
    workflow_rows.seed()

    with _patched(_workflow(next_state_id=None)):
        result = await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=broadcast
        )
    assert result.is_error is False
    assert "completed" in result.first_text()
    assert result.meta == {"workflow_id": "wf-1", "workflow_name": "Workflow wf-1"}
    broadcast.assert_awaited_once()


async def test_transition_with_artifact_storage(session, workflow_rows, artifact_rows):
    workflow_rows.seed()

    with _patched(_workflow(next_state_id="st-2", artifact_id="my-artifact")):
        result = await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {"key": "value"}
        )
    assert result.is_error is False

    [art] = artifact_rows.find(session_id="s-1")
    assert art.artifact_id == "my-artifact"
    assert art.content == {"key": "value"}


async def test_transition_truncate_on_entry_marks_messages_and_broadcasts(broadcast, session, workflow_rows, message_rows):
    workflow_rows.seed()
    make_message("s-1", "user", "pre-truncation")

    with _patched(_workflow(next_state_id="st-2", truncate_on_entry=True)):
        result = await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=broadcast
        )

    assert result.is_error is False
    assert "truncated" in result.first_text()

    assert not any(m.truncated for m in _messages(message_rows))

    await apply_pending_context_actions(session, broadcast)

    assert all(m.truncated for m in _messages(message_rows))

    event_types = [call.args[0].type for call in broadcast.await_args_list]
    assert "truncated" in event_types


async def test_transition_injects_artifacts_as_user_message(broadcast, session, workflow_rows, message_rows):
    make_artifact(
        "s-1", workflow_id="wf-1", state_id="st-0",
        outcome="success", artifact_id="prd",
        content={"document": "The PRD body."},
    )
    workflow_rows.seed()

    wf = _workflow(next_state_id="st-2", truncate_on_entry=True, include_artifacts=["prd"])

    with _patched(wf):
        await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=broadcast
        )
    await apply_pending_context_actions(session, broadcast)

    msgs = _messages(message_rows, live_only=True)
    assert len(msgs) == 1
    assert msgs[0].role == "user"
    text = cast("dict[str, Any]", msgs[0].content[0])["text"]
    assert "prd" in text
    assert "The PRD body." in text


async def test_transition_without_truncate_still_injects_artifacts(broadcast, session, workflow_rows, message_rows):
    make_artifact(
        "s-1", workflow_id="wf-1", state_id="st-0",
        outcome="success", artifact_id="prd",
        content={"document": "body"},
    )
    workflow_rows.seed()
    make_message("s-1", "user", "keep me")

    wf = _workflow(next_state_id="st-2", truncate_on_entry=False, include_artifacts=["prd"])

    with _patched(wf):
        await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=broadcast
        )
    await apply_pending_context_actions(session, broadcast)

    assert len(_messages(message_rows, live_only=True)) == 2


async def test_transition_next_state_not_found_in_workflow(session):
    broken_os = OutputSchema(
        outcome="done",
        next_state="ghost-state",
        schema={"type": "object", "properties": {}},
    )
    wf = Workflow(
        id="wf-1", name="WF", description="d", initial_state="st-1",
        states=[WorkflowState(id="st-1", name="One", prompt="p", output_schemas=[broken_os])],
    )

    with _patched(wf):
        result = await handle_workflow_transition(session, "wf-1", "st-1", "done", {})
    assert result.is_error is True
    assert "ghost-state" in result.first_text()


async def test_transition_no_broadcast_when_none(session, workflow_rows):
    workflow_rows.seed()

    with _patched(_workflow(next_state_id="st-2")):
        result = await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=None
        )
    assert result.is_error is False


async def test_transition_enqueues_pending_action_when_truncating(broadcast, session, workflow_rows, message_rows):
    workflow_rows.seed()
    make_message("s-1", "assistant", "triggering msg")

    with _patched(_workflow(next_state_id="st-2", truncate_on_entry=True)):
        await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=broadcast
        )

    assert not any(m.truncated for m in _messages(message_rows))

    assert "s-1" in _pending_context_actions
    assert len(_pending_context_actions["s-1"]) == 1
    assert _pending_context_actions["s-1"][0].truncate_on_entry is True


async def test_transition_does_not_enqueue_when_no_context_change(broadcast, session, workflow_rows):
    workflow_rows.seed()

    with _patched(_workflow(next_state_id="st-2", truncate_on_entry=False)):
        await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=broadcast
        )

    assert "s-1" not in _pending_context_actions


async def test_apply_pending_preserves_tool_result_pair(broadcast, session, workflow_rows, message_rows):
    make_artifact(
        "s-1", workflow_id="wf-1", state_id="st-1",
        outcome="success", artifact_id="prd",
        content={"document": "body"},
    )
    workflow_rows.seed()
    make_message(
        "s-1", "assistant",
        content=[
            {"type": "text", "text": "transitioning"},
            {"type": "tool_use", "id": "tu-123",
             "name": "workflow_transition_success", "input": {}},
        ],
        stop_reason="tool_use",
    )

    wf = _workflow(next_state_id="st-2", truncate_on_entry=True, include_artifacts=["prd"])

    with _patched(wf):
        await handle_workflow_transition(
            session, "wf-1", "st-1", "done", {}, broadcast=broadcast
        )

    make_message("s-1", "user", content=[{
        "type": "tool_result", "tool_use_id": "tu-123",
        "content": [{"type": "text", "text": "Transitioned"}],
        "is_error": False,
    }])

    await apply_pending_context_actions(session, broadcast)

    live = _messages(message_rows, live_only=True)

    assert len(live) == 1
    assert live[0].role == "user"
    text = cast("dict[str, Any]", live[0].content[0])["text"]
    assert "prd" in text

    assert "s-1" not in _pending_context_actions


async def test_apply_pending_no_queue_is_noop(broadcast, session):
    await apply_pending_context_actions(session, broadcast)
    broadcast.assert_not_awaited()


def test_discard_pending():
    _pending_context_actions["s-1"] = cast(list, [object()])  # type: ignore[assignment]
    discard_pending_context_actions("s-1")
    assert "s-1" not in _pending_context_actions

    discard_pending_context_actions("no-such-session")


async def test_deactivate_workflow(workflow_rows):
    workflow_rows.seed()
    await deactivate_workflow("s-1")
    assert workflow_rows.active("s-1") is None


def test_load_artifacts_returns_matching():
    make_artifact("s-1", state_id="st-1", artifact_id="art-a", content={"data": 1})
    make_artifact("s-1", state_id="st-2", artifact_id="art-b", content={"data": 2})

    results = load_artifacts("s-1", ["art-a"])
    assert len(results) == 1
    aid, content, ts = results[0]
    assert aid == "art-a"
    assert content == {"data": 1}
    assert isinstance(ts, str)

    assert len(load_artifacts("s-1", ["art-a", "art-b"])) == 2


@pytest.mark.parametrize("requested", [["nonexistent"], []])
def test_load_artifacts_empty(requested):
    assert load_artifacts("s-1", requested) == []
