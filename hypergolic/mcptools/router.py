import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hypergolic.mcptools.client.manager import get_mcp_manager
from hypergolic.mcptools.errors import describe_exception
from hypergolic.mcptools.schemas import MCPServerInfo
from hypergolic.mcptools.sessions import (
    get_enabled_servers,
    sessions_using,
    set_enabled_servers,
)
from hypergolic.harness.app.state import get_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


def _resolve_project_path(project_id: str | None) -> str | None:
    if not project_id:
        return None

    try:
        return get_app().get_project(project_id).path
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Project {project_id!r} not found"
        ) from None


def _build_server_info(
    name: str,
    source: str,
    connected: bool,
    tool_count: int,
    transport: str = "stdio",
    auth_type: str = "none",
    auth_status: str = "not_required",
) -> MCPServerInfo:
    return MCPServerInfo(
        name=name,
        source=source,
        connected=connected,
        tool_count=tool_count,
        transport=transport,
        auth_type=auth_type,
        auth_status=auth_status,
    )


@router.get("/servers", response_model=list[MCPServerInfo])
def list_mcp_servers(project_id: str | None = None):
    manager = get_mcp_manager()
    project_path = _resolve_project_path(project_id)
    available = manager.get_available_servers(project_path)
    result = []
    for name, (config, source) in available.items():
        connected_server = manager.get_connected_server(name)
        auth_status = manager.get_auth_status(name, project_path)
        result.append(
            _build_server_info(
                name=name,
                source=source,
                connected=connected_server is not None,
                tool_count=len(connected_server.tools) if connected_server else 0,
                transport=config.transport,
                auth_type=config.auth.type,
                auth_status=auth_status,
            )
        )
    return result


class ToggleMCPRequest(BaseModel):
    session_id: str


@router.post("/servers/{server_name}/connect", response_model=MCPServerInfo)
async def connect_mcp_server(server_name: str, req: ToggleMCPRequest, project_id: str | None = None):
    manager = get_mcp_manager()
    project_path = _resolve_project_path(project_id)
    try:
        server = await manager.connect(server_name, project_path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        detail = describe_exception(e)
        logger.error("MCP connect failed for '%s': %s", server_name, detail)
        raise HTTPException(status_code=502, detail=detail)

    enabled = get_enabled_servers(req.session_id)
    enabled.add(server_name)
    set_enabled_servers(req.session_id, enabled)

    available = manager.get_available_servers(project_path)
    config, source = available.get(server_name, (None, server.source))

    return _build_server_info(
        name=server.name,
        source=server.source,
        connected=True,
        tool_count=len(server.tools),
        transport=config.transport if config else "stdio",
        auth_type=config.auth.type if config else "none",
        auth_status="ready" if config and config.auth.type != "none" else "not_required",
    )


@router.post("/servers/{server_name}/disconnect", response_model=MCPServerInfo)
async def disconnect_mcp_server(server_name: str, req: ToggleMCPRequest, project_id: str | None = None):
    manager = get_mcp_manager()
    project_path = _resolve_project_path(project_id)
    available = manager.get_available_servers(project_path)
    config, source = available.get(server_name, (None, "user"))
    source = source if config else "user"

    enabled = get_enabled_servers(req.session_id)
    enabled.discard(server_name)
    set_enabled_servers(req.session_id, enabled)

    if not sessions_using(server_name):
        await manager.disconnect(server_name)

    return _build_server_info(
        name=server_name,
        source=source,
        connected=manager.is_connected(server_name),
        tool_count=0,
        transport=config.transport if config else "stdio",
        auth_type=config.auth.type if config else "none",
        auth_status=manager.get_auth_status(server_name, project_path),
    )


@router.get("/sessions/{session_id}/enabled", response_model=list[str])
def get_session_enabled_servers(session_id: str):
    return list(get_enabled_servers(session_id))
