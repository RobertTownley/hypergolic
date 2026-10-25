from contextlib import AsyncExitStack

from mcp import ClientSession
from hypergolic.mcptools.client.session import LenientClientSession
from mcp.client.session import MessageHandlerFnT
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from hypergolic.config.schemas import MCPServerConfig
from hypergolic.mcptools.client.auth import build_http_auth
from hypergolic.mcptools.client.http import make_http_client


async def connect_streamable_http(
    server_name: str,
    config: MCPServerConfig,
    exit_stack: AsyncExitStack,
    message_handler: MessageHandlerFnT | None = None,
) -> ClientSession:
    if not config.url:
        raise ValueError("streamable_http transport requires 'url'")

    headers, auth = build_http_auth(server_name, config)
    client = make_http_client(headers=headers, auth=auth)

    transport = await exit_stack.enter_async_context(
        streamable_http_client(url=config.url, http_client=client)
    )
    read_stream, write_stream = transport
    return await exit_stack.enter_async_context(
        LenientClientSession(read_stream, write_stream, message_handler=message_handler)
    )


async def connect_sse(
    server_name: str,
    config: MCPServerConfig,
    exit_stack: AsyncExitStack,
    message_handler: MessageHandlerFnT | None = None,
) -> ClientSession:
    if not config.url:
        raise ValueError("sse transport requires 'url'")

    headers, auth = build_http_auth(server_name, config)

    transport = await exit_stack.enter_async_context(
        sse_client(
            url=config.url,
            headers=headers,
            auth=auth,
            httpx_client_factory=make_http_client,
        )
    )
    read_stream, write_stream = transport
    return await exit_stack.enter_async_context(
        LenientClientSession(read_stream, write_stream, message_handler=message_handler)
    )
