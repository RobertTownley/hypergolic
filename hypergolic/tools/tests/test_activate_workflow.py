import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hypergolic.harness.primitives.bundles import Workflow, WorkflowState
from hypergolic.tools.activate_workflow import (
    ACTIVATE_WORKFLOW_DESCRIPTION,
    build_activate_workflow_command,
    handle_activate_workflow,
)
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.workflows.engine import WorkflowError
from tests._factories import build_output_schema, build_session as _session
from tests.conftest import make_project, make_session


def _ctx(broadcast) -> ToolContext:
    make_project("p-1")
    make_session(project_id="p-1", sid="s-1")
    return ToolContext(
        session=_session(),
        broadcast=broadcast,
        tool_id="activate_workflow",
    )


def _inp(workflow_id: str) -> MagicMock:
    inp = MagicMock()
    inp.workflow_id = workflow_id
    return inp


def _workflow(
    wf_id: str = "wf-1",
    state_id: str = "st-1",
    with_prompt_path: bool = False,
) -> Workflow:
    state = WorkflowState(
        id=state_id,
        name="Initial",
        prompt=None if with_prompt_path else "p",
        prompt_path="/tmp/prompt.md" if with_prompt_path else None,
        output_schemas=[build_output_schema()],
    )
    return Workflow(
        id=wf_id,
        name="My Workflow",
        description="A cool workflow",
        initial_state=state_id,
        states=[state],
    )


async def test_handle_session_already_has_workflow(broadcast):
    ctx = _ctx(broadcast)
    with patch(
        "hypergolic.tools.activate_workflow.get_session_workflow",
        return_value=("wf-existing", "st-1"),
    ):
        result = await handle_activate_workflow(_inp("wf-1"), ctx)

    assert result.is_error is True
    assert "already has active workflow" in result.first_text()


async def test_handle_workflow_not_found(broadcast):
    ctx = _ctx(broadcast)
    with (
        patch("hypergolic.tools.activate_workflow.get_session_workflow", return_value=None),
        patch("hypergolic.tools.activate_workflow.get_workflow", return_value=None),
    ):
        result = await handle_activate_workflow(_inp("wf-missing"), ctx)

    assert result.is_error is True
    assert "not found" in result.first_text()


async def test_handle_workflow_error_from_engine(broadcast):
    ctx = _ctx(broadcast)
    with (
        patch("hypergolic.tools.activate_workflow.get_session_workflow", return_value=None),
        patch("hypergolic.tools.activate_workflow.get_workflow", return_value=_workflow()),
        patch(
            "hypergolic.tools.activate_workflow.activate_workflow",
            side_effect=WorkflowError("engine blew up"),
        ),
    ):
        result = await handle_activate_workflow(_inp("wf-1"), ctx)

    assert result.is_error is True
    assert "engine blew up" in result.first_text()


@pytest.mark.parametrize("with_prompt_path", [False, True])
async def test_handle_successful_activation(broadcast, with_prompt_path):
    ctx = _ctx(broadcast)
    wf = _workflow(with_prompt_path=with_prompt_path)

    with (
        patch("hypergolic.tools.activate_workflow.get_session_workflow", return_value=None),
        patch("hypergolic.tools.activate_workflow.get_workflow", return_value=wf),
        patch("hypergolic.tools.activate_workflow.activate_workflow", new_callable=AsyncMock),
    ):
        result = await handle_activate_workflow(_inp("wf-1"), ctx)

    assert result.is_error is False
    text = result.first_text()
    assert "My Workflow" in text
    assert "activated" in text
    assert "Initial" in text
    assert "st-1" in text
    if with_prompt_path:
        assert "prompt" in text.lower()


def test_build_activate_workflow_command_returns_none_when_no_workflows():
    assert build_activate_workflow_command([]) is None


def test_build_activate_workflow_command_enumerates_workflow_ids():
    command = build_activate_workflow_command(["wf-1", "wf-2"])
    assert command is not None
    assert command.id == "activate_workflow"
    assert command.description == ACTIVATE_WORKFLOW_DESCRIPTION
    assert "wf-1" not in command.description

    assert command.input_schema is not None
    schema = command.input_schema.model_json_schema()
    assert "wf-1" in str(schema) and "wf-2" in str(schema)
