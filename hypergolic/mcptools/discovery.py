"""Configured MCP servers as `apropos` entries.

A server's tools are runtime data: until a session connects, `mcp list` shows an
empty tool list, and an agent concludes the capability does not exist. The
server's declared description and tags are known before any connection, so they
are indexed here, and a hit answers with the line that connects it.
"""

from __future__ import annotations

from hypergolic.harness.primitives.tool import Tool

#: Marks a search entry as a configured server rather than a command.
MCP_SERVER_ORIGIN = "mcp-server"


def server_commands(project_path: str | None) -> list[Tool]:
    from hypergolic.mcptools.client.manager import get_mcp_manager

    servers = get_mcp_manager().get_available_servers(project_path)
    return [
        Tool(
            id=name,
            name=name,
            description=config.description or f"MCP server {name}",
            tags=[*config.tags, "mcp"],
            usage=f"mcp activate {name}",
            origin=MCP_SERVER_ORIGIN,
        )
        for name, (config, _source) in servers.items()
    ]
