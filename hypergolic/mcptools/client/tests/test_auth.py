from typing import Literal

from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

import httpx2
import pytest

from hypergolic.mcptools.client.auth import BrowserOAuthClientProvider, StrictOAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata


def make_provider(
    auth_method: Literal["none", "client_secret_post", "client_secret_basic"],
) -> StrictOAuthClientProvider:
    class NullStorage:
        async def get_tokens(self):
            return None

        async def set_tokens(self, tokens):
            pass

        async def get_client_info(self):
            return None

        async def set_client_info(self, client_info):
            pass


    provider = StrictOAuthClientProvider(
        server_url="https://example.com/mcp",
        client_metadata=OAuthClientMetadata(
            redirect_uris=[AnyUrl("http://localhost:3030/callback")]
        ),
        storage=NullStorage(),
    )
    provider.context.client_info = OAuthClientInformationFull(
        client_id="abc",
        client_secret="shh",
        redirect_uris=[AnyUrl("http://localhost:3030/callback")],
        token_endpoint_auth_method=auth_method,
    )
    return provider


def test_basic_auth_strips_client_id_from_body():
    provider = make_provider("client_secret_basic")
    data, headers = provider.context.prepare_token_auth(
        {"grant_type": "authorization_code", "client_id": "abc"}, {}
    )
    assert headers["Authorization"].startswith("Basic ")
    assert "client_id" not in data
    assert "client_secret" not in data


def test_post_auth_keeps_client_id_in_body():
    provider = make_provider("client_secret_post")
    data, headers = provider.context.prepare_token_auth(
        {"grant_type": "authorization_code", "client_id": "abc"}, {}
    )
    assert "Authorization" not in headers
    assert data["client_id"] == "abc"
    assert data["client_secret"] == "shh"


def test_none_auth_keeps_client_id_in_body():
    provider = make_provider("none")
    data, headers = provider.context.prepare_token_auth(
        {"grant_type": "authorization_code", "client_id": "abc"}, {}
    )
    assert "Authorization" not in headers
    assert data["client_id"] == "abc"


class RecordingLogin:
    def __init__(self) -> None:
        self.finished: list[BaseException | None] = []

    async def open_browser(self, url: str) -> None: ...

    async def wait_for_callback(self): ...

    def finish(self, error: BaseException | None = None) -> None:
        self.finished.append(error)


def browser_provider(flow) -> tuple[BrowserOAuthClientProvider, RecordingLogin]:
    login = RecordingLogin()
    provider = BrowserOAuthClientProvider(
        server_url="https://example.com/mcp",
        client_metadata=OAuthClientMetadata(redirect_uris=[AnyUrl("http://localhost:3030/callback")]),
        storage=make_provider("none").context.storage,
        login=login,  # ty: ignore[invalid-argument-type]
    )
    provider._auth_flow = flow
    return provider, login


async def _drive(provider: BrowserOAuthClientProvider) -> None:
    flow = provider.async_auth_flow(httpx2.Request("POST", "https://example.com/mcp"))
    request = await flow.__anext__()
    try:
        while True:
            request = await flow.asend(httpx2.Response(200, request=request))
    except StopAsyncIteration:
        pass


async def test_a_flow_that_completes_reports_success_to_the_login():
    async def flow(request):
        yield request  # e.g. the token request
        yield request  # the retried MCP request

    provider, login = browser_provider(flow)
    await _drive(provider)
    assert login.finished == [None]


async def test_a_flow_that_raises_reports_the_error_to_the_login():
    async def flow(request):
        yield request
        raise RuntimeError("State parameter mismatch")

    provider, login = browser_provider(flow)
    with pytest.raises(RuntimeError, match="State parameter mismatch"):
        await _drive(provider)
    assert [str(e) for e in login.finished] == ["State parameter mismatch"]
