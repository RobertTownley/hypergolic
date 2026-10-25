"""MCPManager: tool-list refresh, OAuth recovery, and session lifetime.

Transport clients open an anyio task group, so the task that enters them must
stay alive for as long as the session is used: the session belongs to a task
of the manager's own, not whichever request asked for the connection.
"""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest
from mcp import types as mcp_types
from mcp.shared.exceptions import MCPError

from hypergolic.config.schemas import MCPAuthConfig, MCPServerConfig
from hypergolic.mcptools.client.manager import MCPManager, _is_stale_oauth_client
from hypergolic.mcptools.client.models import ConnectedServer
from hypergolic.mcptools import oauth

TOOL_LIST_CHANGED = mcp_types.ToolListChangedNotification()
HTTP_CONNECT = "hypergolic.mcptools.client.manager.connect_streamable_http"
HTTP_CONFIG = MCPServerConfig(transport="streamable_http", url="http://localhost:8080/mcp")


def _tool(name: str) -> mcp_types.Tool:
    return mcp_types.Tool(name=name, description=name, input_schema={"type": "object"})


def _manager_for(monkeypatch, config=HTTP_CONFIG) -> MCPManager:
    """A manager that knows one server, 'srv', with the given config."""
    manager = MCPManager()
    monkeypatch.setattr(
        manager, "get_available_servers", lambda project_path=None: {"srv": (config, "user")}
    )
    return manager


def _manager_with_server(tools: list[str]) -> tuple[MCPManager, MagicMock, ConnectedServer]:
    manager = MCPManager()
    session = MagicMock()
    server = ConnectedServer(name="srv", source="user", session=session, tools=[_tool(t) for t in tools])
    manager._servers["srv"] = server
    return manager, session, server


def _live_session(tools: list[str] = ["t"]) -> MagicMock:
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(
        return_value=mcp_types.ListToolsResult(tools=[_tool(t) for t in tools])
    )
    return session


def _tool_result(text: str) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(content=[mcp_types.TextContent(type="text", text=text)])


@asynccontextmanager
async def _tracked_transport(state: dict):
    state["open"] = True
    try:
        yield
    finally:
        state["open"] = False


def _live_manager(monkeypatch, sessions: list[MagicMock]) -> tuple[MCPManager, list[dict]]:
    """A manager whose one server hands out ``sessions`` in order."""
    manager = _manager_for(monkeypatch)
    transports: list[dict] = []

    async def fake_connect(srv_name, cfg, exit_stack, message_handler=None):
        state: dict = {}
        transports.append(state)
        await exit_stack.enter_async_context(_tracked_transport(state))
        return sessions.pop(0)

    monkeypatch.setattr(HTTP_CONNECT, fake_connect)
    return manager, transports


async def test_tool_list_changed_notification_refreshes_tools():
    manager, session, server = _manager_with_server(["a"])
    session.list_tools = AsyncMock(
        return_value=mcp_types.ListToolsResult(tools=[_tool("a"), _tool("b"), _tool("c")])
    )
    await manager._make_message_handler("srv")(TOOL_LIST_CHANGED)
    await asyncio.sleep(0)  # let the background task run

    session.list_tools.assert_awaited_once()
    assert [t.name for t in server.tools] == ["a", "b", "c"]


@pytest.mark.parametrize("message", [
    mcp_types.ResourceListChangedNotification(),
    object(),  # anything else that reaches the handler is ignored
], ids=["unrelated-notification", "non-notification"])
async def test_other_messages_do_not_trigger_refresh(message):
    manager, session, server = _manager_with_server(["a"])
    session.list_tools = AsyncMock()
    await manager._make_message_handler("srv")(message)
    session.list_tools.assert_not_called()
    assert [t.name for t in server.tools] == ["a"]


async def test_handler_for_unknown_server_is_noop():
    """If the server was disconnected before the notification arrives, drop it."""
    await MCPManager()._make_message_handler("gone")(TOOL_LIST_CHANGED)  # must not raise


async def test_refresh_failure_keeps_existing_tools():
    manager, session, server = _manager_with_server(["a"])
    session.list_tools = AsyncMock(side_effect=RuntimeError("boom"))
    await manager._make_message_handler("srv")(TOOL_LIST_CHANGED)
    assert [t.name for t in server.tools] == ["a"]


async def test_refresh_tools_explicit_updates_cache():
    manager, session, server = _manager_with_server(["old"])
    session.list_tools = AsyncMock(
        return_value=mcp_types.ListToolsResult(tools=[_tool("x"), _tool("y")])
    )
    returned = await manager.refresh_tools("srv")
    assert [t.name for t in returned] == ["x", "y"]
    assert [t.name for t in server.tools] == ["x", "y"]


async def test_refresh_tools_unknown_server_raises():
    with pytest.raises(ValueError, match="not connected"):
        await MCPManager().refresh_tools("nope")


async def test_connect_wires_handler_that_refreshes(monkeypatch):
    """End-to-end: connect installs a handler that refreshes server.tools in place."""
    manager = _manager_for(monkeypatch)
    session = MagicMock()
    session.initialize = AsyncMock()
    tool_lists = [["meta1", "meta2"], ["meta1", "meta2", "sub1", "sub2"]]

    async def fake_list_tools():
        names = tool_lists.pop(0) if len(tool_lists) > 1 else tool_lists[0]
        return mcp_types.ListToolsResult(tools=[_tool(n) for n in names])

    session.list_tools = fake_list_tools
    captured: dict = {}

    async def fake_connect(srv_name, cfg, exit_stack, message_handler=None):
        captured["handler"] = message_handler
        return session

    monkeypatch.setattr(HTTP_CONNECT, fake_connect)

    server = await manager.connect("srv")
    assert [t.name for t in server.tools] == ["meta1", "meta2"]

    await captured["handler"](TOOL_LIST_CHANGED)
    await asyncio.sleep(0)
    assert [t.name for t in server.tools] == ["meta1", "meta2", "sub1", "sub2"]


@pytest.mark.parametrize("exc,expected", [
    (RuntimeError("OAuth failed: invalid_client"), True),
    (RuntimeError("client_id is not registered. Register via POST /oauth/register first."), True),
    # Wrapped in (nested) exception groups the inner error is still found.
    (ExceptionGroup("transport", [RuntimeError("unrelated"),
                                  RuntimeError("token exchange failed: invalid_client")]), True),
    # `unauthorized_client` is grant-type-not-permitted; re-registering won't fix it.
    (RuntimeError("unauthorized_client"), False),
    (RuntimeError("connection refused"), False),
    (TimeoutError("OAuth callback timed out"), False),
])
def test_is_stale_oauth_client(exc, expected):
    assert _is_stale_oauth_client(exc) is expected


def _oauth_manager(monkeypatch, tmp_path, connect_fn):
    """Manager configured with one oauth server whose transport is connect_fn."""

    monkeypatch.setattr(oauth, "TOKEN_DIR", tmp_path)
    config = MCPServerConfig(
        transport="streamable_http", url="http://localhost:8080/mcp",
        auth=MCPAuthConfig(type="oauth"),
    )
    manager = _manager_for(monkeypatch, config)
    monkeypatch.setattr(HTTP_CONNECT, connect_fn)
    storage_dir = tmp_path / "srv"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return manager, storage_dir


async def test_connect_clears_stale_oauth_credentials_and_retries(monkeypatch, tmp_path):
    """First attempt fails with `invalid_client`; manager wipes the cached
    credentials and retries once, succeeding on the second attempt."""
    session = _live_session(["ok"])
    attempts = {"n": 0}

    async def fake_connect(srv_name, cfg, exit_stack, message_handler=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError(
                'OAuth token refresh failed: {"error":"invalid_client",'
                '"error_description":"client_id is not registered."}'
            )
        return session

    manager, storage_dir = _oauth_manager(monkeypatch, tmp_path, fake_connect)
    tokens_path = storage_dir / "tokens.json"
    client_info_path = storage_dir / "client_info.json"
    tokens_path.write_text("{}")
    client_info_path.write_text("{}")

    server = await manager.connect("srv")

    assert attempts["n"] == 2
    assert [t.name for t in server.tools] == ["ok"]
    assert not tokens_path.exists() and not client_info_path.exists()


async def test_connect_does_not_clear_credentials_for_non_oauth_failures(monkeypatch, tmp_path):
    attempts = {"n": 0}

    async def fake_connect(srv_name, cfg, exit_stack, message_handler=None):
        attempts["n"] += 1
        raise RuntimeError("connection refused")

    manager, storage_dir = _oauth_manager(monkeypatch, tmp_path, fake_connect)
    tokens_path = storage_dir / "tokens.json"
    tokens_path.write_text("{}")

    with pytest.raises(RuntimeError, match="connection refused"):
        await manager.connect("srv")
    assert attempts["n"] == 1
    assert tokens_path.exists()


async def test_session_outlives_the_task_that_asked_for_it(monkeypatch):
    manager, transports = _live_manager(monkeypatch, [_live_session()])

    # Connect from a task that then finishes, as a tool call does.
    server = await asyncio.create_task(manager.connect("srv", project_path="/p"))
    for _ in range(3):
        await asyncio.sleep(0)

    assert transports[0]["open"] is True
    assert manager.is_connected("srv")
    assert server.project_path == "/p"

    await manager.disconnect("srv")
    assert transports[0]["open"] is False
    assert not manager.is_connected("srv")


async def test_a_second_connect_reuses_the_live_session(monkeypatch):
    manager, transports = _live_manager(monkeypatch, [_live_session()])
    first = await manager.connect("srv")
    second = await manager.connect("srv")
    assert first is second
    assert len(transports) == 1
    await manager.shutdown()
    assert not manager.get_all_connected()


async def test_a_closed_transport_is_replaced_rather_than_kept(monkeypatch):
    """The bug this exists for: a dead session that still looked connected made
    every later call fail identically, including after reactivating."""
    dead, live = _live_session(), _live_session()
    dead.call_tool = AsyncMock(side_effect=anyio.ClosedResourceError)
    live.call_tool = AsyncMock(return_value=_tool_result("ok"))
    manager, transports = _live_manager(monkeypatch, [dead, live])

    await manager.connect("srv")
    result = await manager.call_tool("srv", "t", {"a": 1})

    assert result == {"content": [{"type": "text", "text": "ok"}], "is_error": False}
    assert len(transports) == 2
    assert transports[0]["open"] is False and transports[1]["open"] is True
    live.call_tool.assert_awaited_once_with("t", {"a": 1})


async def test_a_session_the_server_forgot_is_replaced(monkeypatch):
    """The gateway answers 404 once it drops our Mcp-Session-Id; the SDK keeps
    sending that id, so only a new session gets calls through again."""
    dead, live = _live_session(), _live_session()
    dead.call_tool = AsyncMock(
        side_effect=MCPError(-32001, "Session not found or expired. Send a new InitializeRequest.")
    )
    live.call_tool = AsyncMock(return_value=_tool_result("ok"))
    manager, transports = _live_manager(monkeypatch, [dead, live])

    await manager.connect("srv")
    result = await manager.call_tool("srv", "t", {"a": 1})

    assert result == {"content": [{"type": "text", "text": "ok"}], "is_error": False}
    assert len(transports) == 2
    assert transports[0]["open"] is False and transports[1]["open"] is True
    await manager.disconnect("srv")


async def test_call_tool_on_an_unconnected_server_raises():
    with pytest.raises(ValueError, match="not connected"):
        await MCPManager().call_tool("srv", "t", {})


async def test_a_session_that_dies_on_its_own_stops_being_connected(monkeypatch):
    manager, _ = _live_manager(monkeypatch, [_live_session()])
    server = await manager.connect("srv")

    # A transport failure surfacing inside the session task, post-connect.
    task = server._task
    assert task is not None
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert not manager.is_connected("srv")


async def test_an_unknown_transport_is_a_connect_failure(monkeypatch):
    config = MCPServerConfig(transport="sse", url="http://localhost:8080/sse")
    object.__setattr__(config, "transport", "carrier-pigeon")
    manager = _manager_for(monkeypatch, config)

    with pytest.raises(ValueError, match="Unknown transport"):
        await manager.connect("srv")
    assert not manager.is_connected("srv")


async def test_sse_servers_connect_through_the_sse_transport(monkeypatch):
    manager = _manager_for(monkeypatch, MCPServerConfig(transport="sse", url="http://localhost:8080/sse"))
    session = _live_session(["sse-tool"])

    async def fake_connect_sse(srv_name, cfg, exit_stack, message_handler=None):
        return session

    monkeypatch.setattr("hypergolic.mcptools.client.manager.connect_sse", fake_connect_sse)

    server = await manager.connect("srv")
    assert [t.name for t in server.tools] == ["sse-tool"]
    await manager.disconnect("srv")


async def test_disconnecting_an_unconnected_server_is_a_noop():
    await MCPManager().disconnect("srv")  # must not raise


async def test_binary_and_opaque_content_blocks_become_text(monkeypatch):
    session = _live_session()
    session.call_tool = AsyncMock(
        return_value=mcp_types.CallToolResult(content=[
            mcp_types.ImageContent(type="image", data="ZGF0YQ==", mime_type="image/png"),
            mcp_types.EmbeddedResource(
                type="resource",
                resource=mcp_types.TextResourceContents(
                    uri="file:///x", text="inner", mime_type="text/plain"
                ),
            ),
        ])
    )
    manager, _ = _live_manager(monkeypatch, [session])
    await manager.connect("srv")

    blocks = (await manager.call_tool("srv", "t", {}))["content"]
    assert blocks[0]["text"] == "[Binary content: image/png]"
    assert "inner" in blocks[1]["text"]


async def test_a_transport_that_fails_on_teardown_still_releases_the_server(monkeypatch):
    manager = _manager_for(monkeypatch)

    @asynccontextmanager
    async def angry_transport():
        yield
        raise RuntimeError("teardown exploded")

    async def fake_connect(srv_name, cfg, exit_stack, message_handler=None):
        await exit_stack.enter_async_context(angry_transport())
        return _live_session()

    monkeypatch.setattr(HTTP_CONNECT, fake_connect)

    await manager.connect("srv")
    await manager.disconnect("srv")
    assert not manager.is_connected("srv")


async def test_cancelling_the_session_task_mid_connect_fails_the_caller(monkeypatch):
    manager = _manager_for(monkeypatch)
    entered = asyncio.Event()

    async def fake_connect(srv_name, cfg, exit_stack, message_handler=None):
        entered.set()
        await asyncio.Event().wait()  # a transport that never finishes handshaking

    monkeypatch.setattr(HTTP_CONNECT, fake_connect)

    connecting = asyncio.create_task(manager.connect("srv"))
    await entered.wait()
    session_task = next(
        t for t in asyncio.all_tasks() if (t.get_name() or "").startswith("mcp-session:")
    )
    session_task.cancel()

    with pytest.raises(RuntimeError, match="closed during connect"):
        await connecting


async def test_a_caller_that_gives_up_mid_connect_stops_the_session_task(monkeypatch):
    """`timeout mcp activate` closes the broker stream, cancelling connect().
    The session task used to keep running without an owner: still in its OAuth
    wait and holding the callback port, so the retry failed to bind it."""
    manager = _manager_for(monkeypatch)
    waiting: dict = {}
    entered = asyncio.Event()

    async def fake_connect(srv_name, cfg, exit_stack, message_handler=None):
        async with _tracked_transport(waiting):
            entered.set()
            await asyncio.Event().wait()  # an OAuth login nobody finishes

    monkeypatch.setattr(HTTP_CONNECT, fake_connect)

    connecting = asyncio.create_task(manager.connect("srv"))
    await entered.wait()
    session_task = next(
        t for t in asyncio.all_tasks() if (t.get_name() or "").startswith("mcp-session:")
    )
    connecting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await connecting

    assert session_task.done()
    assert waiting["open"] is False

    # The lock is free and nothing is left over: a retry connects.
    async def live_connect(srv_name, cfg, exit_stack, message_handler=None):
        return _live_session()

    monkeypatch.setattr(HTTP_CONNECT, live_connect)
    assert (await manager.connect("srv")).name == "srv"
    await manager.disconnect("srv")


async def test_concurrent_callers_share_one_replacement_session(monkeypatch):
    """Whoever loses the race must not tear down the session that just replaced
    the dead one."""
    dead, live = _live_session(), _live_session()
    dead.call_tool = AsyncMock(side_effect=anyio.ClosedResourceError)
    live.call_tool = AsyncMock(return_value=_tool_result("ok"))
    manager, transports = _live_manager(monkeypatch, [dead, live])
    await manager.connect("srv")

    first, second = await asyncio.gather(
        manager.call_tool("srv", "t", {}), manager.call_tool("srv", "t", {})
    )

    assert first == second == {"content": [{"type": "text", "text": "ok"}], "is_error": False}
    assert len(transports) == 2
    assert transports[0]["open"] is False and transports[1]["open"] is True
    assert live.call_tool.await_count == 2
    await manager.disconnect("srv")


async def test_a_failure_that_is_not_the_transport_is_not_retried(monkeypatch):
    session = _live_session()
    session.call_tool = AsyncMock(side_effect=RuntimeError("bad request"))
    manager, transports = _live_manager(monkeypatch, [session])
    await manager.connect("srv")

    with pytest.raises(RuntimeError, match="bad request"):
        await manager.call_tool("srv", "t", {})
    assert len(transports) == 1
