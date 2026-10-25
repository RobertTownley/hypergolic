from pydantic import BaseModel


class MCPServerInfo(BaseModel):
    name: str
    source: str  # "user" or "project"
    connected: bool
    tool_count: int
    transport: str = "stdio"
    auth_type: str = "none"
    auth_status: str = "not_required"

