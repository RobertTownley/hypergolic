from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hypergolic.mcptools.sessions import enabled_servers_by_session
from tests.conftest import make_project

def _mock_config(transport: str = "stdio", auth_type: str = "none") -> SimpleNamespace:
    return SimpleNamespace(transport=transport, auth=SimpleNamespace(type=auth_type))


def _mock_tool(name: str, description: str = "", schema: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=description,
        input_schema=schema or {"type": "object"},
    )


def _mock_server(
    name: str,
    source: str = "user",
    tools: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(name=name, source=source, tools=tools or [])


def _make_manager(**overrides) -> MagicMock:
    mgr = MagicMock()
    mgr.get_available_servers = MagicMock(return_value=overrides.get("available", {}))
    mgr.get_connected_server = MagicMock(return_value=overrides.get("connected", None))
    mgr.get_auth_status = MagicMock(return_value=overrides.get("auth_status", "not_required"))
    mgr.connect = AsyncMock(return_value=overrides.get("connect_result", None))
    mgr.disconnect = AsyncMock()
    mgr.is_connected = MagicMock(return_value=overrides.get("is_connected", False))
    return mgr


def _req(api_client, mgr, method: str, url: str, **kwargs):
    with patch("hypergolic.mcptools.router.get_mcp_manager", return_value=mgr):
        return getattr(api_client, method)(url, **kwargs)


@pytest.fixture(autouse=True)
def _clean_enabled_servers():
    enabled_servers_by_session.clear()
    yield

def test_list_servers_empty(api_client):
    resp = _req(api_client, _make_manager(available={}), "get", "/api/mcp/servers")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_servers_with_entries(api_client):
    available = {"my-server": (_mock_config(), "user")}
    server_obj = _mock_server("my-server", tools=[_mock_tool("greet")])
    mgr = _make_manager(available=available, connected=server_obj, auth_status="not_required")
    resp = _req(api_client, mgr, "get", "/api/mcp/servers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "my-server"
    assert data[0]["source"] == "user"
    assert data[0]["connected"] is True
    assert data[0]["tool_count"] == 1
    assert data[0]["transport"] == "stdio"
    assert data[0]["auth_type"] == "none"
    assert data[0]["auth_status"] == "not_required"

def test_connect_server_success(api_client):
    server_obj = _mock_server("srv", tools=[_mock_tool("t1")])
    mgr = _make_manager(available={"srv": (_mock_config(), "user")}, connect_result=server_obj)
    resp = _req(
        api_client, mgr, "post", "/api/mcp/servers/srv/connect",
        json={"session_id": "sess-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "srv"
    assert data["connected"] is True
    assert data["tool_count"] == 1
    # Session should now have this server enabled
    assert "srv" in enabled_servers_by_session.get("sess-1", set())


def test_connect_server_not_found(api_client):
    mgr = _make_manager()
    mgr.connect = AsyncMock(side_effect=ValueError("MCP server 'nope' not found"))
    resp = _req(
        api_client, mgr, "post", "/api/mcp/servers/nope/connect",
        json={"session_id": "sess-1"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


@pytest.mark.parametrize(
    "error,detail",
    [
        (RuntimeError("connection refused"), "connection refused"),
        # ExceptionGroup with a nested ExceptionGroup extracts the inner error.
        (ExceptionGroup("connect errors", [ExceptionGroup("inner group", [OSError("socket closed")])]),
         "socket closed"),
        # ExceptionGroup with only simple exceptions falls back to first exception.
        (ExceptionGroup("connect errors", [OSError("plain error")]), "plain error"),
    ],
    ids=["plain", "nested-group", "simple-group"],
)
def test_connect_server_error(api_client, error, detail):
    mgr = _make_manager()
    mgr.connect = AsyncMock(side_effect=error)
    resp = _req(
        api_client, mgr, "post", "/api/mcp/servers/broken/connect",
        json={"session_id": "sess-1"},
    )
    assert resp.status_code == 502
    assert detail in resp.json()["detail"]


def test_connect_with_project_id(api_client):
    make_project(pid="proj-mcp", name="MCPProj", path="/tmp/mcptest")
    server_obj = _mock_server("proj-srv", source="project", tools=[])
    mgr = _make_manager(
        available={"proj-srv": (_mock_config(), "project")}, connect_result=server_obj
    )
    resp = _req(
        api_client, mgr, "post",
        "/api/mcp/servers/proj-srv/connect?project_id=proj-mcp",
        json={"session_id": "sess-2"},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "project"
    # Manager should have been called with the resolved project path
    mgr.connect.assert_awaited_once_with("proj-srv", "/tmp/mcptest")

def test_disconnect_server(api_client):
    enabled_servers_by_session["sess-d"] = {"disc-srv"}
    mgr = _make_manager(available={"disc-srv": (_mock_config(), "user")})
    resp = _req(
        api_client, mgr, "post", "/api/mcp/servers/disc-srv/disconnect",
        json={"session_id": "sess-d"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "disc-srv"
    assert data["connected"] is False
    # Session should no longer have this server
    assert "disc-srv" not in enabled_servers_by_session.get("sess-d", set())
    # Since no other session uses it, disconnect should have been called
    mgr.disconnect.assert_awaited_once_with("disc-srv")


def test_disconnect_server_still_needed(api_client):
    """If another session still uses the server, manager.disconnect is NOT called."""
    enabled_servers_by_session["sess-a"] = {"shared-srv"}
    enabled_servers_by_session["sess-b"] = {"shared-srv"}
    mgr = _make_manager(
        available={"shared-srv": (_mock_config(), "user")}, is_connected=True
    )
    resp = _req(
        api_client, mgr, "post", "/api/mcp/servers/shared-srv/disconnect",
        json={"session_id": "sess-a"},
    )
    assert resp.status_code == 200
    # Server still connected because sess-b needs it
    mgr.disconnect.assert_not_awaited()


def test_disconnect_unknown_server(api_client):
    """Disconnect a server not in available config — uses defaults."""
    mgr = _make_manager(available={})
    resp = _req(
        api_client, mgr, "post", "/api/mcp/servers/unknown/disconnect",
        json={"session_id": "sess-u"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "unknown"
    assert data["source"] == "user"  # fallback
    assert data["transport"] == "stdio"  # fallback

def test_get_session_enabled_servers(api_client):
    enabled_servers_by_session["sess-x"] = {"alpha", "beta"}
    resp = api_client.get("/api/mcp/sessions/sess-x/enabled")
    assert resp.status_code == 200
    assert set(resp.json()) == {"alpha", "beta"}


def test_get_session_enabled_servers_empty(api_client):
    resp = api_client.get("/api/mcp/sessions/sess-none/enabled")
    assert resp.status_code == 200
    assert resp.json() == []

def test_list_servers_with_bad_project_id(api_client):
    """project_id that doesn't exist in DB → 404."""
    resp = _req(api_client, _make_manager(), "get", "/api/mcp/servers?project_id=nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
