import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx2
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata
from pydantic import AnyUrl

from hypergolic.config.schemas import MCPServerConfig
from hypergolic.mcptools.oauth import FileTokenStorage, OAUTH_REDIRECT_URI, OAuthLogin


class StrictOAuthClientProvider(OAuthClientProvider):
    """Workaround for a bug in mcp (still present in 2.2.0): the SDK leaves `client_id` in the
    token-request body even when it authenticates via HTTP Basic
    (`client_secret_basic`). RFC 6749 §2.3.1 forbids using more than one
    client authentication method per request, and strict authorization
    servers (e.g. Ory Hydra) reject the exchange with
    "Client must not use multiple authentication methods".
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        inner = self.context.prepare_token_auth

        def prepare_token_auth(
            data: dict[str, str], headers: dict[str, str] | None = None
        ) -> tuple[dict[str, str], dict[str, str]]:
            data, headers = inner(data, headers)
            if headers.get("Authorization", "").startswith("Basic "):
                data = {k: v for k, v in data.items() if k != "client_id"}
            return data, headers

        self.context.prepare_token_auth = prepare_token_auth  # ty: ignore[invalid-assignment]


class BrowserOAuthClientProvider(StrictOAuthClientProvider):
    """Tells the login's browser tab how the flow ended.

    The SDK checks state and issuer and exchanges the code only after the
    callback handler returns, so the tab cannot know the outcome by itself.
    The flow ending normally means the token was stored; any exception, or
    httpx closing the flow on a transport error, means it failed.
    """

    def __init__(self, *args: Any, login: OAuthLogin, **kwargs: Any) -> None:
        super().__init__(
            *args,
            redirect_handler=login.open_browser,
            callback_handler=login.wait_for_callback,
            **kwargs,
        )
        self._login = login

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        flow = super().async_auth_flow(request)
        try:
            outgoing = await flow.__anext__()
            while True:
                response = yield outgoing
                outgoing = await flow.asend(response)
        except StopAsyncIteration:
            self._login.finish()
        except BaseException as exc:
            self._login.finish(exc)
            raise
        finally:
            await flow.aclose()


def build_http_auth(
    server_name: str, config: MCPServerConfig
) -> tuple[dict[str, str] | None, Any]:
    auth_config = config.auth
    headers: dict[str, str] | None = None
    auth: httpx2.Auth | None = None

    if auth_config.type == "token":
        token = resolve_token(auth_config)
        if token:
            prefix = auth_config.token_prefix
            value = f"{prefix} {token}" if prefix else token
            headers = {auth_config.token_header: value}

    elif auth_config.type == "oauth":
        storage = FileTokenStorage(server_name)
        redirect_uri = AnyUrl(OAUTH_REDIRECT_URI)
        client_metadata = OAuthClientMetadata(
            redirect_uris=[redirect_uri],
            client_name="Hypergolic",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        )
        auth = BrowserOAuthClientProvider(
            server_url=config.url or "",
            client_metadata=client_metadata,
            storage=storage,
            login=OAuthLogin(),
        )

    return headers, auth


def resolve_token(auth_config: Any) -> str | None:
    if auth_config.token_env_var:
        return os.environ.get(auth_config.token_env_var)
    return None
