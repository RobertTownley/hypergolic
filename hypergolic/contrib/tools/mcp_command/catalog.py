from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from hypergolic.contrib.tools.mcp_command.parse import _align_to_schema
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.tools.approval import resolve_mcp_policy

if TYPE_CHECKING:
    from hypergolic.mcptools.client.models import ConnectedServer

logger = logging.getLogger(__name__)
TOOLSET_SEPARATOR = "__"


def refresh_tools(ctx: ToolContext) -> None:
    """Regenerate ``/tools`` so the change is visible in this very shell.

    Activating a server is the case the design is built for: capability appears
    as files rather than as a rewritten tool list, and the tree is a bind mount,
    so the next clause of the caller's ``&&`` chain already sees it.
    """
    from hypergolic.commands.materialize import sync
    from hypergolic.commands.registry import session_commands

    sync(ctx.session.id, session_commands(ctx.session))


def find_tool(server: ConnectedServer, name: str | None):
    return next((t for t in server.tools if t.name == name), None)


async def tool_list_changed(server: ConnectedServer, timeout: float) -> bool:
    try:
        await asyncio.wait_for(server.tools_changed.wait(), timeout)
    except TimeoutError:
        return False
    return True


async def resync_tools(ctx: ToolContext, server_name: str) -> None:
    from hypergolic.mcptools.client.manager import get_mcp_manager

    try:
        await get_mcp_manager().refresh_tools(server_name)
    except Exception:
        logger.warning("mcp refresh_tools '%s' failed", server_name, exc_info=True)
        return
    refresh_tools(ctx)


def _switch_name(server: ConnectedServer) -> str:
    from hypergolic.mcptools.client.manager import get_mcp_manager

    entry = get_mcp_manager().get_available_servers(server.project_path).get(server.name)
    return entry[0].toolset_switch if entry else ""


def _exposed(server: ConnectedServer) -> set[str]:
    names = (t.name.partition(TOOLSET_SEPARATOR) for t in server.tools)
    return {prefix for prefix, sep, _ in names if sep}


def keep_toolsets(
    server: ConnectedServer, tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    switch = find_tool(server, tool_name)
    if not switch or tool_name != _switch_name(server):
        return arguments
    kept = {name: True for name in server.toolsets | _exposed(server)}
    kept = _align_to_schema(kept, switch.input_schema or {}, [])
    return kept | arguments


def remember_toolsets(server: ConnectedServer, tool_name: str, arguments: dict[str, Any]) -> None:
    if tool_name == _switch_name(server):
        server.toolsets = {name for name, on in arguments.items() if on is True}


async def enable_toolset(ctx: ToolContext, server: ConnectedServer, tool_name: str | None) -> bool:
    from hypergolic.mcptools.client.manager import get_mcp_manager

    switch_name = _switch_name(server)
    toolset, sep, _ = (tool_name or "").partition(TOOLSET_SEPARATOR)
    if not (switch_name and sep and find_tool(server, switch_name)):
        return False
    arguments = keep_toolsets(server, switch_name, {toolset: True})
    policy = resolve_mcp_policy(server.name, switch_name, arguments, ctx.session)
    if policy.decision != "ALLOW":
        return False
    result = await get_mcp_manager().call_tool(server.name, switch_name, arguments)
    if result.get("is_error"):
        return False
    remember_toolsets(server, switch_name, arguments)
    await resync_tools(ctx, server.name)
    return True
