import asyncio
from dataclasses import dataclass, field

from mcp import ClientSession
from mcp.types import Tool as MCPTool


@dataclass
class ConnectedServer:
    """A live session plus the handles that end it.

    The transport belongs to a task of its own (``MCPManager._run_session``), so
    shutdown is signalling ``_stop`` and awaiting ``_task``.
    """

    name: str
    source: str
    session: ClientSession
    tools: list[MCPTool]
    _stop: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task | None = None
    tools_changed: asyncio.Event = field(default_factory=asyncio.Event)
    project_path: str | None = None
    toolsets: set[str] = field(default_factory=set)
