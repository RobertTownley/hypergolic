import logging
from typing import Any

from pydantic import BaseModel, create_model

from hypergolic.harness.primitives.bundles import OutputSchema
from hypergolic.schemas import Session
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.workflows.resolver import get_session_workflow, get_workflow
from hypergolic.workflows.engine import handle_workflow_transition

logger = logging.getLogger(__name__)

PYTHON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def _json_schema_to_pydantic_fields(
    schema: dict[str, Any],
) -> dict[str, Any]:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}

    for name, prop in properties.items():
        prop_type = prop.get("type", "string")

        if prop_type == "array":
            python_type: type = list[str]
        elif prop_type == "object":
            python_type = dict[str, Any]
        else:
            python_type = PYTHON_TYPE_MAP.get(prop_type, str)

        if name in required:
            fields[name] = (python_type, ...)
        else:
            fields[name] = (python_type | None, None)

    return fields


def _build_transition_tool(
    workflow_id: str,
    state_id: str,
    output_schema: OutputSchema,
    state_name: str,
) -> Tool:
    outcome = output_schema.outcome
    tool_id = f"workflow_transition_{outcome}"

    fields: dict[str, Any] = _json_schema_to_pydantic_fields(output_schema.schema_def)
    if not fields:
        fields = {"_placeholder": (str | None, None)}
    InputModel = create_model(f"WorkflowTransition_{outcome}_Input", **fields)

    next_desc = f" \u2192 {output_schema.next_state}" if output_schema.next_state else " \u2192 exit workflow"
    description = (
        f"Complete the '{state_name}' state with outcome '{outcome}'{next_desc}"
    )

    _wf_id = workflow_id
    _state_id = state_id
    _outcome = outcome

    async def _handle(inp: BaseModel, ctx: ToolContext) -> ToolResult:
        output_data = inp.model_dump(mode="json")
        output_data.pop("_placeholder", None)

        return await handle_workflow_transition(
            session=ctx.session,
            workflow_id=_wf_id,
            from_state_id=_state_id,
            outcome=_outcome,
            output=output_data,
            broadcast=ctx.broadcast,
        )

    return Tool(
        id=tool_id,
        name=f"Workflow Transition: {outcome}",
        description=description,
        input_schema=InputModel,
        run=_handle,
        approval=always("REQUIRE_APPROVAL" if output_schema.requires_approval else "ALLOW"),
        approval_view=output_schema.approval_view,
    )


def build_transition_tools(session: Session) -> tuple[list[Tool], str | None]:
    """Build workflow transition tools for a session's current state.

    Returns ``(tools, current_state_id)``. ``current_state_id`` is ``None``
    when no workflow is active, and is still returned when the workflow or
    state lookup fails — callers use it to attribute the (possibly empty)
    tool list to a specific state for reason tracking.
    """
    wf_state = get_session_workflow(session.id)
    if wf_state is None:
        return [], None

    workflow_id, current_state_id = wf_state
    wf = get_workflow(workflow_id)
    if wf is None:
        logger.warning("Active workflow '%s' not found in config", workflow_id)
        return [], current_state_id

    state = next((s for s in wf.states if s.id == current_state_id), None)
    if state is None:
        logger.warning("Active state '%s' not found in workflow '%s'", current_state_id, workflow_id)
        return [], current_state_id

    tools = [
        _build_transition_tool(
            workflow_id=workflow_id,
            state_id=current_state_id,
            output_schema=output_schema,
            state_name=state.name,
        )
        for output_schema in state.output_schemas
    ]
    return tools, current_state_id
