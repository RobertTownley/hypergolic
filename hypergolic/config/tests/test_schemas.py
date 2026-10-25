"""Tests for hypergolic.config.schemas."""

from typing import Any, cast

import pytest
from pydantic import ValidationError

from hypergolic.config.schemas import MCPAuthConfig, MCPServerConfig


def test_mcp_auth_config_defaults():
    config = MCPAuthConfig()
    assert config.type == "none"
    assert config.token_env_var is None
    assert config.token_header == "Authorization"
    assert config.token_prefix == "Bearer"


def test_mcp_auth_config_token_type():
    config = MCPAuthConfig(type="token", token_env_var="MY_TOKEN")
    assert config.type == "token"
    assert config.token_env_var == "MY_TOKEN"


def test_mcp_auth_config_oauth_type():
    config = MCPAuthConfig(type="oauth")
    assert config.type == "oauth"


def test_mcp_auth_config_custom_header():
    config = MCPAuthConfig(type="token", token_header="X-Custom-Auth", token_prefix="Token")
    assert config.token_header == "X-Custom-Auth"
    assert config.token_prefix == "Token"


def test_mcp_auth_config_invalid_type():
    with pytest.raises(ValidationError):
        MCPAuthConfig(type=cast(Any, "invalid"))


def test_mcp_server_config_defaults():
    config = MCPServerConfig()
    assert config.transport == "streamable_http"
    assert config.url is None
    assert isinstance(config.auth, MCPAuthConfig)
    assert config.auth.type == "none"


def test_mcp_server_config_stdio_rejected():
    with pytest.raises(ValidationError):
        MCPServerConfig(transport=cast(Any, "stdio"))


def test_mcp_server_config_http():
    config = MCPServerConfig(
        transport="streamable_http",
        url="http://localhost:8080/mcp",
        auth=MCPAuthConfig(type="token", token_env_var="MCP_TOKEN"),
    )
    assert config.transport == "streamable_http"
    assert config.url == "http://localhost:8080/mcp"
    assert config.auth.type == "token"


def test_mcp_server_config_sse():
    config = MCPServerConfig(
        transport="sse",
        url="http://localhost:9000/events",
    )
    assert config.transport == "sse"


def test_mcp_server_config_invalid_transport():
    with pytest.raises(ValidationError):
        MCPServerConfig(transport=cast(Any, "invalid"))


def test_mcp_server_config_no_command_field():
    config = MCPServerConfig(transport="streamable_http", url="http://localhost:8080/mcp")
    assert not hasattr(config, "command")
    assert not hasattr(config, "args")
    assert not hasattr(config, "env")


def test_mcp_server_config_auth_dict():
    """Auth can be passed as a dict and gets coerced to MCPAuthConfig."""
    config = MCPServerConfig(
        transport="streamable_http",
        url="http://localhost:8080",
        auth=cast(Any, {"type": "oauth"}),
    )
    assert config.auth.type == "oauth"
