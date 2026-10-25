from typing import Literal

from pydantic import BaseModel, Field


class MCPAuthConfig(BaseModel):
    type: Literal["none", "token", "oauth"] = "none"
    token_env_var: str | None = None
    token_header: str = "Authorization"
    token_prefix: str = "Bearer"


class MCPServerConfig(BaseModel):
    transport: Literal["streamable_http", "sse"] = "streamable_http"
    url: str | None = None
    auth: MCPAuthConfig = Field(default_factory=MCPAuthConfig)
    #: `mcp list` prints it and `apropos` searches it, so an agent can find a
    #: server before it connects — a server's tool list is empty until then.
    description: str = ""
    #: Extra `apropos` vocabulary: the nouns a user names when they need it.
    tags: list[str] = Field(default_factory=list)
    toolset_switch: str = ""

