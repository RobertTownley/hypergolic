"""The single tool a session ships over the wire.

It takes a shell string and hands it to the container as-is. There is no
``argv[0]`` matching, no registry lookup, no ``shlex`` round trip, and no
fall-through precedence — capability is discovered from ``/tools`` on ``PATH``
and invoked through the broker, so the tool has nothing left to resolve.

The container itself remains the boundary, so the string is auto-approved unless
the project's sandbox says otherwise; individual commands inside it are gated by
their own policies when they reach the broker.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from hypergolic.commands.registry import sandbox_shell, shell_capable_containers
from hypergolic.harness.bridge import evaluate_harness_approval, invoke_tool
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.schemas import Session
from hypergolic.commands.materialize import sync
from hypergolic.commands.registry import session_commands


CMD_ID = "cmd"
CMD_NAME = "Command"
CMD_DESCRIPTION = "Run sandbox container commands"


def _chosen_container(inp: BaseModel) -> str | None:
    chosen = getattr(inp, "container", None)
    return chosen.value if isinstance(chosen, Enum) else chosen


def _shell_input(sandbox: Tool, inp: BaseModel) -> BaseModel | None:
    """Adapt to the sandbox tool's own schema.

    A multi-container sandbox requires a ``container``; absent an explicit choice
    the first declared one is used, which is what the single-container case does
    implicitly.
    """
    schema = sandbox.input_schema
    if schema is None:
        return None
    fields = schema.model_fields
    command = getattr(inp, "command")
    payload: dict[str, object] = {}
    if "commands" in fields:
        payload["commands"] = [command]
    if "command" in fields:
        payload["command"] = command
    if "container" in fields:
        container = _chosen_container(inp)
        if container is not None:
            payload["container"] = container
        else:
            members = getattr(fields["container"].annotation, "__members__", None)
            if members:
                payload["container"] = next(iter(members.values()))
    return schema.model_validate(payload)


async def _run_cmd(inp: BaseModel, ctx: ToolContext) -> ToolResult:
    session = ctx.session
    sandbox = sandbox_shell(session)
    if sandbox is None:
        return ToolResult.text(
            "No sandbox is available in this session, so there is nowhere to run "
            "a command.",
            is_error=True,
        )

    problem = _sync_tools(session)
    sub_ctx = ToolContext(
        session=session, broadcast=ctx.broadcast, tool_id=sandbox.id,
        tool_use_id=ctx.tool_use_id,
    )
    result = await invoke_tool(sandbox, _shell_input(sandbox, inp), sub_ctx)
    return result.append_text(problem) if problem else result


def _sync_tools(session: Session) -> str | None:
    """Refresh ``/tools`` before the exec that will read it.

    ``/tools`` is a bind mount of a host directory, so rewriting it here is
    visible to the already-running container immediately — so enabling an MCP
    server mid-session adds executables and index lines, never tool schemas: the
    wire tool list is fixed for the session either way.
    """

    return sync(session.id, session_commands(session))


def _approve_cmd(actx: ApprovalContext) -> ToolApprovalDecision:
    """Defer to the sandbox's own declared policy for the string as a whole.

    Arbitrary shell in a container is the model today, but a harness is free to
    gate its sandbox, and reading the tool's own policy keeps `cmd` from silently
    widening it. Commands *inside* the string are gated separately, per command,
    at the moment each is reached.
    """
    sandbox = sandbox_shell(actx.session)
    if sandbox is None:
        return ToolApprovalDecision(decision="ALLOW")
    payload = {}
    shell_input = _shell_input(sandbox, actx.input)
    if shell_input is not None:
        payload = shell_input.model_dump(mode="json")
    return evaluate_harness_approval(sandbox, payload, actx.session)


def build_cmd_tool(session: Session) -> Tool:
    """The wire tool for this session, carrying only the choices it really has.

    One container is the common case, and then `container` is not a choice at
    all — the field is omitted and exec targets that container implicitly. With
    several, the ids become a required enum, so the schema itself is the list of
    what can be targeted.
    """
    containers = shell_capable_containers(session)

    if len(containers) > 1:
        ContainerEnum = Enum(  # type: ignore[misc]
            "ContainerEnum", {cid: cid for cid in containers}, type=str
        )

        class CmdInput(InputSchema):
            command: str
            container: ContainerEnum  # type: ignore[valid-type]
    else:

        class CmdInput(InputSchema):  # type: ignore[no-redef]
            command: str

    return Tool(
        id=CMD_ID,
        name=CMD_NAME,
        description=CMD_DESCRIPTION,
        input_schema=CmdInput,
        run=_run_cmd,
        approval=_approve_cmd,
        requires_worktree=True,
    )
