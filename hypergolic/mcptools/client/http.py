import os
import ssl
from typing import Any

import certifi
import httpx2
from mcp.shared._httpx_utils import MCP_DEFAULT_SSE_READ_TIMEOUT, MCP_DEFAULT_TIMEOUT

_CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS")


def _find_extra_ca_file() -> str | None:
    for var in _CA_ENV_VARS:
        path = os.environ.get(var)
        if path and os.path.isfile(path):
            return path
    return None


def make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    extra_ca = _find_extra_ca_file()
    if extra_ca:
        ctx.load_verify_locations(cafile=extra_ca)
    ctx.verify_flags &= ~ssl.VerifyFlags.VERIFY_X509_STRICT
    return ctx


def make_http_client(
    headers: dict[str, str] | None = None,
    timeout: httpx2.Timeout | None = None,
    auth: httpx2.Auth | None = None,
) -> httpx2.AsyncClient:
    kwargs: dict[str, Any] = {
        "follow_redirects": True,
        "verify": make_ssl_context(),
    }
    kwargs["timeout"] = timeout or httpx2.Timeout(
        MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT
    )
    if headers is not None:
        kwargs["headers"] = headers
    if auth is not None:
        kwargs["auth"] = auth
    return httpx2.AsyncClient(**kwargs)
