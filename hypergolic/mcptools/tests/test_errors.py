"""An empty error message is worse than no error at all: the agent reads it as
a call that succeeded and returned nothing."""

import anyio
import pytest

from mcp.shared.exceptions import MCPError

from hypergolic.mcptools.errors import (
    describe_exception,
    is_session_expired,
    is_transport_closed,
    needs_reconnect,
)


@pytest.mark.parametrize(
    "exc,expected",
    [
        (RuntimeError("boom"), "boom"),
        (anyio.ClosedResourceError(), "ClosedResourceError: the MCP session's transport is closed"),
        (anyio.BrokenResourceError(), "BrokenResourceError: the MCP session's transport is closed"),
        (ValueError(), "ValueError"),
        # Transports wrap what they raise in task groups, whose own message only
        # counts sub-exceptions.
        (ExceptionGroup("unhandled errors in a TaskGroup", [RuntimeError("401 Unauthorized")]),
         "401 Unauthorized"),
        (ExceptionGroup("g", [RuntimeError("same"), RuntimeError("same")]), "same"),
        (ExceptionGroup("g", [ValueError(), anyio.ClosedResourceError()]),
         "ValueError; ClosedResourceError: the MCP session's transport is closed"),
    ],
    ids=["message", "closed", "broken", "silent-other", "group", "deduped-group", "mixed-group"],
)
def test_every_exception_renders_as_something(exc, expected):
    assert describe_exception(exc) == expected


@pytest.mark.parametrize(
    "exc,expected",
    [
        (anyio.ClosedResourceError(), True),
        (ExceptionGroup("g", [ExceptionGroup("inner", [anyio.BrokenResourceError()])]), True),
        (RuntimeError("boom"), False),
        (ExceptionGroup("g", [RuntimeError("boom")]), False),
    ],
    ids=["direct", "nested-group", "unrelated", "unrelated-group"],
)
def test_a_wrapped_closed_transport_is_still_a_closed_transport(exc, expected):
    assert is_transport_closed(exc) is expected


@pytest.mark.parametrize(
    "exc,expected",
    [
        (MCPError(-32001, "Session not found or expired. Send a new InitializeRequest."), True),
        # The SDK's stand-in when the 404 body is not JSON-RPC.
        (MCPError(-32600, "Session terminated"), True),
        (ExceptionGroup("g", [MCPError(-32600, "Session terminated")]), True),
        (MCPError(-32602, "Invalid params"), False),
        # Only the server's own error counts; a tool's text that says it does not.
        (RuntimeError("Session not found"), False),
    ],
    ids=["gateway", "sdk-fallback", "group", "other-mcp-error", "not-mcp"],
)
def test_a_forgotten_session_is_recognized(exc, expected):
    assert is_session_expired(exc) is expected
    assert needs_reconnect(exc) is expected


def test_a_closed_transport_also_needs_a_reconnect():
    assert needs_reconnect(anyio.ClosedResourceError())
