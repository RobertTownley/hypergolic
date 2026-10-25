"""Turning transport failures into something an agent can act on.

The anyio errors that surface when an MCP session's streams are gone
(``ClosedResourceError``, ``BrokenResourceError``) carry no message at all, and
the transports wrap whatever they raise in anyio task groups, so interpolating
an exception produced either ``gateway set-toolsets:`` or ``unhandled
errors in a TaskGroup (1 sub-exception)`` — both indistinguishable from a call
that succeeded and returned nothing useful. Every path that renders an MCP
exception goes through :func:`describe_exception`.
"""

from __future__ import annotations

import anyio
from mcp.shared.exceptions import MCPError

#: The session's streams are gone; the connection cannot be reused.
TRANSPORT_CLOSED = (anyio.ClosedResourceError, anyio.BrokenResourceError)


def is_transport_closed(exc: BaseException) -> bool:
    if isinstance(exc, BaseExceptionGroup):
        return any(is_transport_closed(sub) for sub in exc.exceptions)
    return isinstance(exc, TRANSPORT_CLOSED)


#: How a lost server-side session reads once the SDK has turned the 404 into an
#: ``MCPError``: the status code is gone, only the message survives. The first
#: is the SDK's own stand-in, the rest are what gateways put in the body.
_SESSION_EXPIRED_MARKERS = (
    "session terminated",
    "session not found",
    "session expired",
    "send a new initializerequest",
)


def is_session_expired(exc: BaseException) -> bool:
    """The server forgot our ``Mcp-Session-Id``; the spec says re-initialize.

    The SDK keeps sending the dead id, so every later call fails identically
    until the session is replaced.
    """
    if isinstance(exc, BaseExceptionGroup):
        return any(is_session_expired(sub) for sub in exc.exceptions)
    if not isinstance(exc, MCPError):
        return False
    message = exc.message.lower()
    return any(marker in message for marker in _SESSION_EXPIRED_MARKERS)


def needs_reconnect(exc: BaseException) -> bool:
    """A fresh session would fix this; the same call is worth one retry."""
    return is_transport_closed(exc) or is_session_expired(exc)


def describe_exception(exc: BaseException) -> str:
    """The most specific message in ``exc``, never the empty string.

    A group is worth reporting only through its contents: the group's own
    message counts sub-exceptions rather than saying what went wrong.
    """
    if isinstance(exc, BaseExceptionGroup):
        described = [describe_exception(sub) for sub in exc.exceptions]
        informative = [d for d in described if d]
        return "; ".join(dict.fromkeys(informative)) or type(exc).__name__
    detail = str(exc)
    if detail:
        return detail
    if isinstance(exc, TRANSPORT_CLOSED):
        return f"{type(exc).__name__}: the MCP session's transport is closed"
    return type(exc).__name__
