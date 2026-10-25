import logging
import re
from typing import Any

from mcp.types import Tool as MCPTool
from pydantic import BaseModel, ConfigDict, create_model, Field

from hypergolic.mcptools.client.manager import get_mcp_manager
from hypergolic.mcptools.errors import describe_exception
from hypergolic.mcptools.json_schema import python_type_for
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.eval_behavior import always_conduct
from hypergolic.harness.primitives.results import CommandResult, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.tools.approval import resolve_mcp_policy

logger = logging.getLogger(__name__)

# BaseModel attributes that would shadow parent if used as field names directly.
_BASEMODEL_RESERVED = frozenset(BaseModel.__dict__) | frozenset(dir(BaseModel))


def _safe_field_name(prop_name: str) -> str:
    """Return a Python-safe field name that won't shadow BaseModel attributes."""
    if prop_name in _BASEMODEL_RESERVED:
        return f"field_{prop_name}"
    return prop_name


def _input_model_name(server_name: str, tool_name: str) -> str:
    return "mcp_" + re.sub(r"\W", "_", f"{server_name}__{tool_name}") + "_Input"


def _build_mcp_input_model(server_name: str, mcp_tool: MCPTool) -> type[BaseModel]:
    schema = mcp_tool.input_schema
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    if not properties:
        return create_model(_input_model_name(server_name, mcp_tool.name))

    field_definitions: dict[str, Any] = {}
    needs_alias = False
    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            prop_schema = {}
        python_type, nullable = python_type_for(prop_schema)
        description = prop_schema.get("description", "")

        field_name = _safe_field_name(prop_name)
        alias = prop_name if field_name != prop_name else None
        if alias:
            needs_alias = True

        is_required = prop_name in required_fields
        annotated_type: Any = python_type | None if (nullable or not is_required) else python_type

        if is_required:
            field_definitions[field_name] = (
                annotated_type,
                Field(alias=alias, description=description) if (alias or description) else ...,
            )
        else:
            default = prop_schema.get("default")
            field_definitions[field_name] = (
                annotated_type,
                Field(default=default, alias=alias, description=description),
            )

    model_config = ConfigDict(populate_by_name=True) if needs_alias else None
    extra: dict[str, Any] = {}
    if model_config is not None:
        extra["__config__"] = model_config

    return create_model(
        _input_model_name(server_name, mcp_tool.name),
        **field_definitions,
        **extra,
    )


def command_id(server_name: str, tool_name: str) -> str:
    """The name the agent types to reach one MCP tool.

    Dotted rather than the ``mcp_server__tool`` shape models are trained to emit
    as tool calls: a dot is not legal in an Anthropic tool name, so the index
    entry cannot read as a wire tool the way the underscored form did — sessions
    burned turns calling names that only exist as files in ``/tools/bin``.
    """
    return f"mcp.{server_name}.{tool_name}"


async def execute_mcp_tool(
    server_name: str, tool_name: str, raw_input: dict[str, Any]
) -> ToolResult:
    manager = get_mcp_manager()

    try:
        result = await manager.call_tool(server_name, tool_name, raw_input)
        return ToolResult(
            content=result["content"],
            is_error=result.get("is_error", False),
        )
    except Exception as e:
        detail = describe_exception(e)
        logger.error(
            "MCP tool '%s %s' failed: %s", server_name, tool_name, detail, exc_info=True
        )
        return ToolResult.text(f"MCP tool error: {detail}", is_error=True)


def build_mcp_tool(server_name: str, mcp_tool: MCPTool) -> Tool:
    """A remote MCP tool as an ordinary command.

    Routing and authorization are closed over here rather than special-cased
    downstream: the harness' ``mcp_approval_policy`` is the policy, and the run
    callable is the client call, so nothing else in the system has to know this
    command came from a server.
    """
    tool_id = command_id(server_name, mcp_tool.name)
    input_model = _build_mcp_input_model(server_name, mcp_tool)
    description = mcp_tool.description or f"MCP tool '{mcp_tool.name}' from server '{server_name}'"

    def approval(ctx: ApprovalContext) -> ToolApprovalDecision:
        payload = ctx.input.model_dump(mode="json", exclude_unset=True) if ctx.input is not None else {}
        return resolve_mcp_policy(server_name, mcp_tool.name, payload, ctx.session)

    async def run(inp: BaseModel | None, _ctx: ToolContext) -> CommandResult:
        payload = inp.model_dump(mode="json", exclude_unset=True) if inp is not None else {}
        result = await execute_mcp_tool(server_name, mcp_tool.name, payload)
        text = "\n".join(block["text"] for block in result.iter_text_blocks())
        if result.is_error:
            return CommandResult(stderr=text, exit_code=1)
        return CommandResult(stdout=text)

    return Tool(
        id=tool_id,
        name=f"{server_name}: {mcp_tool.name}",
        description=description,
        input_schema=input_model,
        run=run,
        approval=approval,
        eval_behavior=always_conduct,
        origin=f"mcp:{server_name}",
    )


def get_mcp_tools_for_session(enabled_servers: set[str]) -> list[Tool]:
    manager = get_mcp_manager()
    tools: list[Tool] = []
    for server_name, server in manager.get_all_connected().items():
        if server_name not in enabled_servers:
            continue
        for mcp_tool in server.tools:
            try:
                tools.append(build_mcp_tool(server_name, mcp_tool))
            except Exception:
                logger.exception(
                    "Failed to build MCP tool '%s' from server '%s'; skipping",
                    mcp_tool.name,
                    server_name,
                )
    return tools
