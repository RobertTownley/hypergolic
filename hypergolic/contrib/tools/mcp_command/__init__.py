"""MCP as one shim command; rationale in parse.py. Public surface for harness configs."""

from hypergolic.contrib.tools.mcp_command.actions import approve_mcp, run_mcp
from hypergolic.contrib.tools.mcp_command.command import mcp_command
from hypergolic.contrib.tools.mcp_command.parse import McpInput, McpOutput, parse_mcp

__all__ = ["McpInput", "McpOutput", "approve_mcp", "mcp_command", "parse_mcp", "run_mcp"]
