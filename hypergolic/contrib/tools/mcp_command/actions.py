from __future__ import annotations

import json
import logging
from typing import Any

from hypergolic.contrib.tools.mcp_command import catalog
from hypergolic.contrib.tools.mcp_command.catalog import (
    enable_toolset,
    find_tool,
    keep_toolsets,
    remember_toolsets,
    resync_tools,
    tool_list_changed,
)
from hypergolic.contrib.tools.mcp_command.parse import (
    _READ_ONLY,
    McpInput,
    _align_to_schema,
)
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.eval_behavior import EvalBehavior
from hypergolic.harness.primitives.results import CommandResult
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.mcptools.sessions import (
    get_enabled_servers,
    sessions_using,
    set_enabled_servers,
)
from hypergolic.tools.approval import resolve_mcp_policy

logger = logging.getLogger(__name__)
TOOL_LIST_SETTLE_S = 0.25


def _aligned_arguments(inp: McpInput) -> dict[str, Any]:
    """Arguments spelled and typed the way the connected server's schema does."""
    from hypergolic.mcptools.client.manager import get_mcp_manager

    server = get_mcp_manager().get_connected_server(inp.server or "")
    tool = next((t for t in server.tools if t.name == inp.tool), None) if server else None
    return _align_to_schema(inp.arguments, (tool.input_schema if tool else None) or {}, inp.literal)


def approve_mcp(ctx: ApprovalContext) -> ToolApprovalDecision:
    """Read-only introspection is free; a call is whatever the harness says.

    Deliberately raises rather than guessing when there is no invocation to judge
    — the generated README then points at this file, which is the real contract.
    """
    inp = ctx.input
    if not isinstance(inp, McpInput):
        raise ValueError("mcp approval depends on the subcommand")
    if inp.action in _READ_ONLY:
        return ToolApprovalDecision(decision="ALLOW")
    if inp.action == "deactivate":
        # Session-local and reversible: it only narrows what this session sees.
        return ToolApprovalDecision(decision="ALLOW")
    if inp.action == "activate":
        return ToolApprovalDecision(
            decision="REQUIRE_APPROVAL",
            reason="connects to an MCP server, which may start an OAuth flow",
        )


    # A policy that inspects arguments must judge what the server will receive,
    # which is the aligned spelling — computed here rather than written back, so
    # deciding stays free of side effects.
    return resolve_mcp_policy(
        inp.server or "", inp.tool or "", _aligned_arguments(inp), ctx.session
    )


async def mcp_eval_behavior(ctx: ApprovalContext) -> EvalBehavior:
    inp = ctx.input
    if isinstance(inp, McpInput) and inp.action == "exec":
        return EvalBehavior.CONDUCT
    return EvalBehavior.EXECUTE


def _server_rows(project_path: str | None, enabled: set[str]) -> list[dict]:
    from hypergolic.mcptools.client.manager import get_mcp_manager

    manager = get_mcp_manager()
    rows = []
    for name, (config, source) in manager.get_available_servers(project_path).items():
        server = manager.get_connected_server(name)
        rows.append(
            {
                "server": name,
                # Before activation "tools" is empty, so this is the only text
                # that says what the server reaches.
                "description": config.description,
                "source": source,
                "status": "active" if name in enabled else (
                    "connected" if manager.is_connected(name) else "available"
                ),
                "tools": [tool.name for tool in server.tools] if server else [],
            }
        )
    return rows


async def run_mcp(inp: McpInput, ctx: ToolContext) -> CommandResult:
    from hypergolic.mcptools.client.manager import get_mcp_manager
    from hypergolic.mcptools.errors import describe_exception

    manager = get_mcp_manager()
    session_id = ctx.session.id
    enabled = get_enabled_servers(session_id)

    if inp.action == "list":
        rows = _server_rows(ctx.session.project_path, enabled)
        if not rows:
            return CommandResult(stdout="No MCP servers configured.\n")
        return CommandResult(stdout=json.dumps(rows, indent=2) + "\n", data={"servers": rows})

    server_name = inp.server or ""

    if inp.action == "activate":
        try:
            server = await manager.connect(server_name, ctx.session.project_path)
        except Exception as exc:
            logger.error("mcp activate '%s' failed", server_name, exc_info=True)
            return CommandResult.fail(
                f"could not connect to '{server_name}': {describe_exception(exc)}\n"
            )
        set_enabled_servers(session_id, enabled | {server_name})
        catalog.refresh_tools(ctx)
        names = ", ".join(tool.name for tool in server.tools) or "none"
        return CommandResult(
            stdout=f"activated '{server_name}'. Tools: {names}\n",
            data={"servers": [{"server": server_name, "tools": [t.name for t in server.tools]}]},
        )

    if inp.action == "deactivate":
        set_enabled_servers(session_id, enabled - {server_name})
        catalog.refresh_tools(ctx)
        # Drop the connection too when nobody else is holding it: an agent that
        # deactivates to recover from a broken server expects the next
        # `activate` to dial afresh, not to hand back the same session.
        if not sessions_using(server_name, exclude=session_id):
            await manager.disconnect(server_name)
        return CommandResult(stdout=f"deactivated '{server_name}'\n")

    server = manager.get_connected_server(server_name)
    if server is None:
        return CommandResult.fail(
            f"'{server_name}' is not connected. Run `mcp activate {server_name}` first.\n"
        )
    tool = find_tool(server, inp.tool)
    if tool is None:
        await resync_tools(ctx, server_name)
        tool = find_tool(server, inp.tool)
    if tool is None and await enable_toolset(ctx, server, inp.tool):
        tool = find_tool(server, inp.tool)
    if tool is None:
        available = ", ".join(t.name for t in server.tools) or "none"
        return CommandResult.fail(
            f"'{server_name}' has no tool '{inp.tool}'. Available: {available}\n"
        )

    if inp.action == "schema":
        schema = tool.input_schema or {}
        return CommandResult(stdout=json.dumps(schema, indent=2) + "\n", data={"input_schema": schema})

    arguments = _align_to_schema(inp.arguments, tool.input_schema or {}, inp.literal)
    arguments = keep_toolsets(server, tool.name, arguments)
    try:
        result = await manager.call_tool(server_name, tool.name, arguments)
    except Exception as exc:
        logger.error("mcp exec '%s %s' failed", server_name, tool.name, exc_info=True)
        return CommandResult.fail(f"{server_name} {tool.name}: {describe_exception(exc)}\n")
    content = result.get("content", [])
    text = "\n".join(block.get("text", "") for block in content if block.get("type") == "text")
    if result.get("is_error"):
        return CommandResult.fail(text or f"{server_name} {tool.name} failed\n")
    remember_toolsets(server, tool.name, arguments)
    if await tool_list_changed(server, TOOL_LIST_SETTLE_S):
        await resync_tools(ctx, server_name)
        text += "\nTool list changed. Tools: " + (", ".join(t.name for t in server.tools) or "none")
    return CommandResult(stdout=(text + "\n") if text else "", data={"content": content})
