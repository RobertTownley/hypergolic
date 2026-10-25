from unittest.mock import AsyncMock

import pytest
from mcp import types

from hypergolic.mcptools.client.session import LenientClientSession


def _session() -> LenientClientSession:
    s = LenientClientSession.__new__(LenientClientSession)
    s._tool_output_schemas = {"t": {"type": "object", "required": ["k"]}}
    s._tool_output_validators = {}
    return s


async def test_missing_structured_content_is_tolerated():
    s = _session()
    s.list_tools = AsyncMock()
    await s.validate_tool_result(
        "t", types.CallToolResult(content=[types.TextContent(type="text", text="x")])
    )


async def test_present_structured_content_is_still_validated():
    s = _session()
    s.list_tools = AsyncMock()
    with pytest.raises(RuntimeError, match="Invalid structured content"):
        await s.validate_tool_result(
            "t", types.CallToolResult(content=[], structured_content={})
        )
