import asyncio
from enum import Enum

from pydantic import BaseModel

from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.workflows.resolver import get_session_workflow, get_workflow
from hypergolic.workflows.engine import activate_workflow, WorkflowError
from hypergolic.commands.argv import positional

ACTIVATE_WORKFLOW_DESCRIPTION = "Enter a structured multi-phase process"


async def handle_activate_workflow(inp: BaseModel, ctx: ToolContext) -> ToolResult:
    workflow_id: str = getattr(inp, "workflow_id")
    session = ctx.session

    existing = await asyncio.to_thread(get_session_workflow, session.id)
    if existing is not None:
        return ToolResult.text(
            f"Session already has active workflow '{existing[0]}'. Deactivate it first.",
            is_error=True,
        )

    wf = get_workflow(workflow_id)
    if wf is None:
        return ToolResult.text(f"Workflow '{workflow_id}' not found.", is_error=True)


    try:
        await activate_workflow(session, workflow_id, ctx.broadcast)
    except WorkflowError as e:
        return ToolResult.text(str(e), is_error=True)

    initial_state = None
    for s in wf.states:
        if s.id == wf.initial_state:
            initial_state = s
            break

    state_desc = ""
    if initial_state:
        state_desc = f"\n\nInitial state: {initial_state.name} ({initial_state.id})"
        if initial_state.prompt_path:
            state_desc += "\nState prompt will be injected into system prompt."

    meta: dict = {"workflow_id": workflow_id, "workflow_name": wf.name}
    if initial_state:
        meta["workflow_state_id"] = initial_state.id
        meta["workflow_state_name"] = initial_state.name

    return ToolResult.text(f"Workflow '{wf.name}' activated.{state_desc}", meta=meta)


def build_activate_workflow_command(workflow_ids: list[str]) -> Tool | None:
    """The ``activate_workflow`` command, enumerating what this session may enter."""
    wf_ids = list(workflow_ids)
    if not wf_ids:
        return None

    WorkflowIdEnum = Enum("WorkflowIdEnum", {wid: wid for wid in wf_ids}, type=str)

    class ActivateWorkflowInput(BaseModel):
        workflow_id: WorkflowIdEnum

    return Tool(
        id="activate_workflow",
        tags=["workflow", "process", "phase", "state-machine", "structured-process"],
        name="Activate Workflow",
        description=ACTIVATE_WORKFLOW_DESCRIPTION,
        input_schema=ActivateWorkflowInput,
        argv=positional("workflow_id"),
        usage="activate_workflow <workflow_id>",
        run=handle_activate_workflow,
    )
