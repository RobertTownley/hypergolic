import asyncio
import logging
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import types as mcp_types

from hypergolic.config.schemas import MCPServerConfig
from hypergolic.harness.app.state import get_app
from hypergolic.mcptools.client.models import ConnectedServer
from hypergolic.mcptools.client.transports import connect_sse, connect_streamable_http
from hypergolic.mcptools.errors import describe_exception, needs_reconnect
from hypergolic.mcptools.oauth import FileTokenStorage

logger = logging.getLogger(__name__)


# Markers that indicate the server has dropped/rotated our client registration.
# Deliberately narrow: `unauthorized_client` is excluded because it's the
# standard OAuth 2.0 code for "grant type not permitted," which would not be
# fixed by re-registering and could otherwise cause a re-register loop.
_STALE_CLIENT_MARKERS = (
    "invalid_client",
    "client_id is not registered",
)


def _is_stale_oauth_client(exc: BaseException) -> bool:
    """Detect OAuth failures caused by a cached client registration the server no longer recognizes.

    The MCP transport runs auth inside anyio task groups, so the relevant error
    can be wrapped in one or more ExceptionGroups before reaching us.
    """
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_stale_oauth_client(sub) for sub in exc.exceptions)
    message = str(exc).lower()
    return any(marker in message for marker in _STALE_CLIENT_MARKERS)


class MCPManager:
    def __init__(self) -> None:
        self._servers: dict[str, ConnectedServer] = {}
        self._lock = asyncio.Lock()

    def get_available_servers(self, project_path: str | None = None) -> dict[str, tuple[MCPServerConfig, str]]:
        raw_servers = get_app()._mcp_servers
        return {
            name: (MCPServerConfig(**config), "user")
            for name, config in raw_servers.items()
        }

    def is_connected(self, server_name: str) -> bool:
        return server_name in self._servers

    def get_connected_server(self, server_name: str) -> ConnectedServer | None:
        return self._servers.get(server_name)

    def get_all_connected(self) -> dict[str, ConnectedServer]:
        return dict(self._servers)

    def get_auth_status(self, server_name: str, project_path: str | None = None) -> str:
        available = self.get_available_servers(project_path)
        if server_name not in available:
            return "unknown"
        config, _ = available[server_name]
        if config.auth.type == "none":
            return "not_required"
        if config.auth.type == "token":
            env_var = config.auth.token_env_var
            if env_var and os.environ.get(env_var):
                return "ready"
            return "missing_token"
        if config.auth.type == "oauth":
            storage = FileTokenStorage(server_name)
            if storage._tokens_path.exists():
                return "ready"
            return "needs_oauth"
        return "unknown"

    async def connect(self, server_name: str, project_path: str | None = None) -> ConnectedServer:
        async with self._lock:
            if server_name in self._servers:
                return self._servers[server_name]
            return await self._connect_unlocked(server_name, project_path)

    async def _connect_unlocked(
        self, server_name: str, project_path: str | None
    ) -> ConnectedServer:
        available = self.get_available_servers(project_path)
        if server_name not in available:
            raise ValueError(f"MCP server '{server_name}' not found in configuration")

        config, source = available[server_name]

        try:
            return await self._open_session(server_name, config, source, project_path)
        except Exception as exc:
            if config.auth.type == "oauth" and _is_stale_oauth_client(exc):
                logger.warning(
                    "MCP server '%s' rejected cached OAuth client; clearing credentials and retrying",
                    server_name,
                )
                FileTokenStorage(server_name).clear()
                try:
                    return await self._open_session(server_name, config, source, project_path)
                except Exception:
                    logger.error(
                        "MCP server '%s' connect failed after clearing stale OAuth credentials",
                        server_name,
                    )
                    raise
            raise

    async def _open_session(
        self,
        server_name: str,
        config: MCPServerConfig,
        source: str,
        project_path: str | None = None,
    ) -> ConnectedServer:
        """Hand the transport to a task that outlives this call.

        The transport clients open an anyio task group, binding the session's
        streams to whichever task entered them. Entering one here and returning
        leaves that context suspended and unowned: finalization tears it down
        and every later ``call_tool`` fails with an empty ``ClosedResourceError``
        — a connected-looking server that cannot be used. The task below holds
        the context open until ``disconnect`` asks it to stop.
        """
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[ConnectedServer] = loop.create_future()
        stop = asyncio.Event()
        task = loop.create_task(
            self._run_session(server_name, config, source, project_path, ready, stop),
            name=f"mcp-session:{server_name}",
        )
        try:
            server = await ready
        except BaseException:
            # A caller that gives up (its broker stream closed, e.g. `timeout`
            # killed the shim) arrives as CancelledError. The session task must
            # stop with it, or it outlives the lock and keeps holding whatever
            # it was waiting on — an OAuth callback port a retry then cannot bind.
            stop.set()
            if ready.cancelled():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        server._task = task
        return server

    async def _run_session(
        self,
        server_name: str,
        config: MCPServerConfig,
        source: str,
        project_path: str | None,
        ready: asyncio.Future[ConnectedServer],
        stop: asyncio.Event,
    ) -> None:
        handler = self._make_message_handler(server_name)
        server: ConnectedServer | None = None
        try:
            async with AsyncExitStack() as exit_stack:
                if config.transport == "streamable_http":
                    session = await connect_streamable_http(
                        server_name, config, exit_stack, handler
                    )
                elif config.transport == "sse":
                    session = await connect_sse(server_name, config, exit_stack, handler)
                else:
                    raise ValueError(f"Unknown transport: {config.transport}")

                await session.initialize()
                tools_result = await session.list_tools()

                server = ConnectedServer(
                    name=server_name,
                    source=source,
                    session=session,
                    tools=tools_result.tools,
                    _stop=stop,
                    project_path=project_path,
                )
                self._servers[server_name] = server
                logger.info(
                    "Connected to MCP server '%s' (%s) with %d tools",
                    server_name, config.transport, len(server.tools),
                )
                ready.set_result(server)
                await stop.wait()
        except Exception as exc:
            if ready.done():
                logger.error(
                    "MCP server '%s' session ended unexpectedly", server_name, exc_info=True
                )
            else:
                logger.error("Failed to connect to MCP server '%s'", server_name, exc_info=True)
                ready.set_exception(exc)
        finally:
            # Only retract our own registration: a reconnect may already have
            # replaced it while this task was unwinding.
            if server is not None and self._servers.get(server_name) is server:
                del self._servers[server_name]
            if not ready.done():
                ready.set_exception(
                    RuntimeError(f"MCP server '{server_name}' session closed during connect")
                )

    def _make_message_handler(self, server_name: str):
        async def handler(message: mcp_types.ServerNotification | Exception) -> None:
            if isinstance(message, mcp_types.ToolListChangedNotification):
                # Must not await here — the receive loop calls this handler
                # synchronously, and refreshing tools issues a new list_tools
                # request which would deadlock waiting on the same loop.
                server = self._servers.get(server_name)
                if server is not None:
                    server.tools_changed.set()
                asyncio.get_running_loop().create_task(self._refresh_server_tools(server_name))

        return handler

    async def _refresh_server_tools(self, server_name: str) -> None:
        server = self._servers.get(server_name)
        if server is None:
            return
        try:
            tools_result = await server.session.list_tools()
        except Exception:
            logger.warning(
                "Failed to refresh tools for MCP server '%s' after list_changed",
                server_name, exc_info=True,
            )
            return
        server.tools = tools_result.tools
        logger.info(
            "Refreshed MCP server '%s' after list_changed (%d tools)",
            server_name, len(server.tools),
        )

    async def refresh_tools(self, server_name: str) -> list[mcp_types.Tool]:
        server = self._servers.get(server_name)
        if server is None:
            raise ValueError(f"MCP server '{server_name}' is not connected")
        server.tools_changed.clear()
        tools_result = await server.session.list_tools()
        server.tools = tools_result.tools
        return list(server.tools)

    async def disconnect(self, server_name: str) -> None:
        async with self._lock:
            server = self._servers.pop(server_name, None)
        if server is None:
            return
        server._stop.set()
        if server._task is not None:
            await asyncio.gather(server._task, return_exceptions=True)
        logger.info("Disconnected from MCP server '%s'", server_name)

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        server = self._servers.get(server_name)
        if not server:
            raise ValueError(f"MCP server '{server_name}' is not connected")

        try:
            result = await server.session.call_tool(tool_name, arguments)
        except Exception as exc:
            if not needs_reconnect(exc):
                raise
            server = await self._reconnect(server_name, server, exc)
            result = await server.session.call_tool(tool_name, arguments)
        # call_tool raises for input-required and claimed results by default.
        assert isinstance(result, mcp_types.CallToolResult)
        content_parts: list[dict[str, Any]] = []
        for item in result.content:
            if hasattr(item, "text"):
                content_parts.append({"type": "text", "text": item.text})
            elif hasattr(item, "data") and hasattr(item, "mime_type"):
                content_parts.append({"type": "text", "text": f"[Binary content: {item.mime_type}]"})
            else:
                content_parts.append({"type": "text", "text": str(item)})

        return {"content": content_parts, "is_error": result.is_error}

    async def _reconnect(
        self, server_name: str, dead: ConnectedServer, cause: BaseException
    ) -> ConnectedServer:
        """A dead session must not survive as a connected-looking one.

        The replacement registers itself over the corpse before that is retired:
        deregistering first leaves a window where a concurrent call is told the
        server is not connected, and lets the loser of the race close the
        session the winner just opened.
        """
        logger.warning(
            "MCP server '%s' session is unusable (%s); reconnecting",
            server_name,
            describe_exception(cause),
        )
        async with self._lock:
            current = self._servers.get(server_name)
            if current is not None and current is not dead:
                return current
            replacement = await self._connect_unlocked(server_name, dead.project_path)
        dead._stop.set()
        if dead._task is not None:
            await asyncio.gather(dead._task, return_exceptions=True)
        return replacement

    async def shutdown(self) -> None:
        names = list(self._servers.keys())
        for name in names:
            await self.disconnect(name)


_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager
