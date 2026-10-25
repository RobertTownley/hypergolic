from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hypergolic.harness.primitives.bundles import OutputSchema, Workflow, WorkflowState
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.workflows.tools import (
    _build_transition_tool,
    _json_schema_to_pydantic_fields,
    build_transition_tools,
)
from tests._factories import approval_of, build_session, build_workflow, invoke
from tests.conftest import make_project, make_session


def _output_schema(
    outcome: str = "done",
    next_state: str | None = None,
    requires_approval: bool = False,
    properties: dict | None = None,
) -> OutputSchema:
    return OutputSchema(
        outcome=outcome,
        next_state=next_state,
        requires_approval=requires_approval,
        schema={"type": "object", "properties": properties or {}},
    )


def _workflow(
    wf_id: str = "wf-1",
    state_id: str = "st-1",
    output_schemas: list[OutputSchema] | None = None,
) -> Workflow:
    return build_workflow(
        wf_id,
        state_id=state_id,
        states=[
            WorkflowState(
                id=state_id,
                name="State One",
                prompt="p",
                output_schemas=output_schemas or [_output_schema()],
            )
        ],
    )


def test_json_schema_to_pydantic_fields_empty():
    fields = _json_schema_to_pydantic_fields({"type": "object", "properties": {}})
    assert fields == {}


@pytest.mark.parametrize(
    "prop, expected_type",
    [
        ({"type": "string"}, str),
        ({"type": "integer"}, int),
        ({"type": "number"}, float),
        ({"type": "boolean"}, bool),
        ({"type": "array"}, list[str]),
        ({"type": "object"}, dict[str, Any]),
        ({"type": "exotic_type"}, str),
        ({}, str),
    ],
)
def test_json_schema_to_pydantic_fields_type_mapping(prop, expected_type):
    schema = {"type": "object", "properties": {"f": prop}, "required": ["f"]}
    python_type, default = _json_schema_to_pydantic_fields(schema)["f"]
    assert python_type == expected_type
    assert default is ...


def test_json_schema_to_pydantic_fields_optional_default_none():
    schema = {"type": "object", "properties": {"notes": {"type": "string"}}}
    _, default = _json_schema_to_pydantic_fields(schema)["notes"]
    assert default is None


def test_build_transition_tool_basic():
    tool = _build_transition_tool(
        workflow_id="wf-1",
        state_id="st-1",
        output_schema=_output_schema("success"),
        state_name="My State",
    )
    assert tool.id == "workflow_transition_success"
    assert "My State" in tool.description
    assert "success" in tool.description


@pytest.mark.parametrize(
    "output_schema, expected_substring",
    [
        (_output_schema("approve", next_state="st-2"), "st-2"),
        (_output_schema("done", next_state=None), "exit workflow"),
    ],
)
def test_build_transition_tool_describes_next_state(output_schema, expected_substring):
    tool = _build_transition_tool(
        workflow_id="wf-1",
        state_id="st-1",
        output_schema=output_schema,
        state_name="Review",
    )
    assert expected_substring in tool.description


def test_build_transition_tool_requires_approval():
    tool = _build_transition_tool(
        workflow_id="wf-1",
        state_id="st-1",
        output_schema=_output_schema("confirm", requires_approval=True),
        state_name="Confirm",
    )
    assert approval_of(tool) == "REQUIRE_APPROVAL"


def test_build_transition_tool_with_fields_in_schema():
    tool = _build_transition_tool(
        workflow_id="wf-1",
        state_id="st-1",
        output_schema=_output_schema(
            "submit",
            properties={"summary": {"type": "string"}, "score": {"type": "integer"}},
        ),
        state_name="Submit",
    )
    assert hasattr(tool.input_schema, "model_fields")


def test_build_transition_tool_empty_schema_uses_placeholder():
    tool = _build_transition_tool(
        workflow_id="wf-1",
        state_id="st-1",
        output_schema=_output_schema("done"),
        state_name="Done",
    )
    assert tool.input_schema is not None
    instance = tool.input_schema.model_validate({"_placeholder": None})
    assert hasattr(instance, "_placeholder")


async def test_build_transition_tool_handle_removes_placeholder(broadcast):
    tool = _build_transition_tool(
        workflow_id="wf-1",
        state_id="st-1",
        output_schema=_output_schema("done"),
        state_name="Done",
    )

    mock_transition = AsyncMock(return_value=MagicMock(is_error=False))
    ctx = ToolContext(session=build_session(), broadcast=broadcast, tool_id=tool.id)
    assert tool.input_schema is not None
    inp = tool.input_schema.model_validate({"_placeholder": None})
    with patch(
        "hypergolic.workflows.tools.handle_workflow_transition",
        new=mock_transition,
    ):
        await invoke(tool, inp, ctx)

    output_data = mock_transition.call_args[1]["output"]
    assert "_placeholder" not in output_data


def test_build_transition_tools_no_active_workflow():
    make_project("p-1")
    make_session(project_id="p-1", sid="s-1")
    session = build_session()

    with patch("hypergolic.workflows.tools.get_session_workflow", return_value=None):
        tools, state_id = build_transition_tools(session)

    assert tools == []
    assert state_id is None


def test_build_transition_tools_workflow_not_found():
    make_project("p-1")
    make_session(project_id="p-1", sid="s-1")
    session = build_session()

    with (
        patch("hypergolic.workflows.tools.get_session_workflow", return_value=("wf-x", "st-1")),
        patch("hypergolic.workflows.tools.get_workflow", return_value=None),
    ):
        tools, state_id = build_transition_tools(session)

    assert tools == []
    assert state_id == "st-1"


def test_build_transition_tools_state_not_found():
    make_project("p-1")
    make_session(project_id="p-1", sid="s-1")
    session = build_session()
    wf = _workflow(state_id="st-1")

    with (
        patch("hypergolic.workflows.tools.get_session_workflow", return_value=("wf-1", "st-missing")),
        patch("hypergolic.workflows.tools.get_workflow", return_value=wf),
    ):
        tools, state_id = build_transition_tools(session)

    assert tools == []
    assert state_id == "st-missing"


def test_build_transition_tools_returns_tools():
    make_project("p-1")
    make_session(project_id="p-1", sid="s-1")
    session = build_session()
    wf = _workflow(
        output_schemas=[_output_schema("approve"), _output_schema("reject")]
    )

    with (
        patch("hypergolic.workflows.tools.get_session_workflow", return_value=("wf-1", "st-1")),
        patch("hypergolic.workflows.tools.get_workflow", return_value=wf),
    ):
        tools, state_id = build_transition_tools(session)

    assert {t.id for t in tools} == {
        "workflow_transition_approve",
        "workflow_transition_reject",
    }
    assert state_id == "st-1"


def test_build_transition_tools_no_output_schemas():
    make_project("p-1")
    make_session(project_id="p-1", sid="s-1")
    session = build_session()
    wf = Workflow(
        id="wf-1", name="WF", description="d", initial_state="st-1",
        states=[WorkflowState(id="st-1", name="S", prompt="p", output_schemas=[])],
    )

    with (
        patch("hypergolic.workflows.tools.get_session_workflow", return_value=("wf-1", "st-1")),
        patch("hypergolic.workflows.tools.get_workflow", return_value=wf),
    ):
        tools, _ = build_transition_tools(session)

    assert tools == []
