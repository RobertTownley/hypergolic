"""Global TLS trust bootstrap.

Corporate networks (e.g. TLS-intercepting proxies) present a self-signed root
CA that lives in the OS trust store but not in certifi's bundle, which the
Anthropic/httpx SDKs use by default. That breaks HTTPS to endpoints whose
chains the proxy rewrites (e.g. Bedrock/Mantle), surfacing as
``APIConnectionError: Connection error.`` from an underlying
``CERTIFICATE_VERIFY_FAILED``.

``truststore`` patches Python's ssl module to verify against the OS trust
store, so every SSL client in the process (Anthropic direct, Bedrock, Mantle,
MCP) transparently trusts whatever the OS trusts.

Injection is process-global and must precede any capture of ``ssl.SSLContext``
— urllib3 and botocore bind it at import time — so ``hypergolic/__init__``
calls ``ensure_truststore()`` before importing anything else, and that is the
only call site.
"""

import ssl
import types

import truststore

_ORIGINAL_SSL_CONTEXT = ssl.SSLContext
if _ORIGINAL_SSL_CONTEXT.__module__ != "ssl":
    raise RuntimeError(
        f"ssl.SSLContext was already patched by {_ORIGINAL_SSL_CONTEXT.__module__} "
        "before ssl_bootstrap was imported; injection order is broken"
    )
_injected = False


def ensure_truststore() -> None:
    """Inject OS-trust-store verification into ssl (idempotent)."""
    global _injected
    if _injected:
        return
    truststore.inject_into_ssl()
    _unshadow_original_context_setters()
    _injected = True


def _unshadow_original_context_setters() -> list[str]:
    # CPython's ssl.SSLContext setters delegate via
    # `super(SSLContext, SSLContext).<name>.__set__`, reading `SSLContext` from
    # the ssl module globals — which truststore rebinds to its own subclass, so
    # the setter re-enters itself forever (RecursionError). botocore
    # deliberately builds contexts from the original class, so every AWS SigV4
    # credential lookup hits it.
    patched = []
    for name, prop in list(vars(_ORIGINAL_SSL_CONTEXT).items()):
        if not isinstance(prop, property) or prop.fset is None:
            continue
        if "SSLContext" not in prop.fset.__code__.co_names:
            continue
        setter_globals = {**prop.fset.__globals__, "SSLContext": _ORIGINAL_SSL_CONTEXT}
        fset = types.FunctionType(
            prop.fset.__code__,
            setter_globals,
            prop.fset.__name__,
            prop.fset.__defaults__,
            prop.fset.__closure__,
        )
        setattr(_ORIGINAL_SSL_CONTEXT, name, property(prop.fget, fset, prop.fdel))
        patched.append(name)
    return patched
