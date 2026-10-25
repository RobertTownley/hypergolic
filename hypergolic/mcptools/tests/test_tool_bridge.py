"""Tests for hypergolic.mcptools.tool_bridge."""

from types import SimpleNamespace
from typing import Any, cast, get_args, get_origin
from unittest.mock import MagicMock, patch

import pytest
from mcp.types import Tool as MCPTool

from hypergolic.mcptools.tool_bridge import (
    _build_mcp_input_model,
    build_mcp_tool,
    get_mcp_tools_for_session,
    command_id,
)
from hypergolic.mcptools.json_schema import python_type_for


def _mcp_tool(name: str, schema: dict[str, Any]) -> MCPTool:
    return cast(MCPTool, SimpleNamespace(name=name, description="desc", input_schema=schema))


@pytest.mark.parametrize(
    "schema,expected_type,expected_nullable",
    [
        ({"type": "string"}, str, False),
        ({"type": "integer"}, int, False),
        ({"type": "number"}, float, False),
        ({"type": "boolean"}, bool, False),
        ({"type": "array"}, list, False),
        ({"type": "object"}, dict, False),
    ],
)
def test_python_type_for_string_types(schema, expected_type, expected_nullable):
    python_type, nullable = python_type_for(schema)
    assert python_type is expected_type
    assert nullable is expected_nullable


def test_python_type_for_nullable_union():
    """JSON Schema nullable idiom: type: ['string', 'null']."""
    python_type, nullable = python_type_for({"type": ["string", "null"]})
    assert python_type is str
    assert nullable is True


def test_python_type_for_nullable_union_other_primitive():
    python_type, nullable = python_type_for({"type": ["integer", "null"]})
    assert python_type is int
    assert nullable is True


def test_python_type_for_multi_type_union_falls_back_to_any():
    python_type, nullable = python_type_for({"type": ["string", "number"]})
    assert python_type is Any
    assert nullable is False


def test_python_type_for_multi_type_union_with_null():
    python_type, nullable = python_type_for({"type": ["string", "number", "null"]})
    assert python_type is Any
    assert nullable is True


def test_python_type_for_reads_any_of():
    python_type, nullable = python_type_for({"anyOf": [{"type": "string"}, {"type": "null"}]})
    assert python_type is str
    assert nullable is True


def test_python_type_for_untyped_variant_stays_any():
    python_type, _ = python_type_for({"anyOf": [{"type": "string"}, {"$ref": "#/$defs/F"}]})
    assert python_type is Any


def test_python_type_for_reads_one_of():
    python_type, nullable = python_type_for({"oneOf": [{"type": "integer"}, {"type": "string"}]})
    assert python_type is Any
    assert nullable is False


def test_python_type_for_unknown_type():
    python_type, nullable = python_type_for({"type": "bizarre"})
    assert python_type is Any
    assert nullable is False


def test_build_input_model_empty_properties():
    model = _build_mcp_input_model("srv", _mcp_tool("t", {"type": "object"}))
    instance = model()
    assert instance.model_dump() == {}


def test_build_input_model_nullable_union_does_not_crash():
    """Regression: list-valued 'type' used to raise TypeError: unhashable type: 'list'."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": ["string", "null"], "description": "optional name"},
        },
        "required": ["name"],
    }
    model = _build_mcp_input_model("srv", _mcp_tool("t", schema))
    # required + nullable → must accept both a string and None
    assert model.model_validate({"name": "hello"}).model_dump() == {"name": "hello"}
    assert model.model_validate({"name": None}).model_dump() == {"name": None}


def test_build_input_model_required_string():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    model = _build_mcp_input_model("srv", _mcp_tool("t", schema))
    assert model.model_validate({"name": "hi"}).model_dump() == {"name": "hi"}
    with pytest.raises(Exception):
        model()


def test_build_input_model_optional_default():
    schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 10}},
    }
    model = _build_mcp_input_model("srv", _mcp_tool("t", schema))
    assert model().model_dump() == {"limit": 10}
    assert model.model_validate({"limit": 5}).model_dump() == {"limit": 5}


def test_build_input_model_reserved_field_name_aliased():
    """Property names that collide with BaseModel attrs get aliased."""
    schema = {
        "type": "object",
        "properties": {"model_config": {"type": "string"}},
        "required": ["model_config"],
    }
    model = _build_mcp_input_model("srv", _mcp_tool("t", schema))
    instance = model(**{"model_config": "cfg"})
    assert getattr(instance, "field_model_config") == "cfg"


def test_build_input_model_missing_type_treated_as_any():
    schema = {
        "type": "object",
        "properties": {
            "payload": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        },
        "required": ["payload"],
    }
    model = _build_mcp_input_model("srv", _mcp_tool("t", schema))
    # Any accepts anything
    assert model.model_validate({"payload": "x"}).model_dump() == {"payload": "x"}
    assert model.model_validate({"payload": 42}).model_dump() == {"payload": 42}


def test_build_input_model_optional_field_is_nullable():
    schema = {
        "type": "object",
        "properties": {"maybe": {"type": "string"}},
    }
    model = _build_mcp_input_model("srv", _mcp_tool("t", schema))
    fields = model.model_fields
    anno = fields["maybe"].annotation
    # str | None is Union[str, None]
    assert get_origin(anno) is not None
    assert type(None) in get_args(anno)


def test_get_mcp_tools_for_session_skips_broken_tool():
    """A single broken tool schema must not take down the whole server."""
    good = _mcp_tool("good", {"type": "object", "properties": {"x": {"type": "string"}}})
    good2 = _mcp_tool("good2", {"type": "object"})

    server = SimpleNamespace(tools=[good, good2])
    manager = MagicMock()
    manager.get_all_connected.return_value = {"srv": server}

    real_build = build_mcp_tool

    def flaky_build(server_name, mcp_tool):
        if mcp_tool.name == "good2":
            raise RuntimeError("synthetic schema failure")
        return real_build(server_name, mcp_tool)

    with (
        patch("hypergolic.mcptools.tool_bridge.get_mcp_manager", return_value=manager),
        patch("hypergolic.mcptools.tool_bridge.build_mcp_tool", side_effect=flaky_build),
    ):
        tools = get_mcp_tools_for_session({"srv"})

    # Only the healthy tool made it through
    assert len(tools) == 1
    assert tools[0].id == "mcp.srv.good"


def test_get_mcp_tools_for_session_skips_disabled():
    server = SimpleNamespace(tools=[_mcp_tool("t", {"type": "object"})])
    manager = MagicMock()
    manager.get_all_connected.return_value = {"srv": server}
    with patch("hypergolic.mcptools.tool_bridge.get_mcp_manager", return_value=manager):
        tools = get_mcp_tools_for_session(set())
    assert tools == []


def test_command_id_is_dotted_not_an_api_tool_name():
    """Dots keep the name from reading as a wire tool the model can call."""
    assert command_id("wiki", "get_users") == "mcp.wiki.get_users"
    assert command_id("acme-gateway", "metrics__query") == "mcp.acme-gateway.metrics__query"


async def test_run_omits_arguments_the_caller_did_not_give():
    """Sending ``null`` for every optional field trips servers that validate
    ``expected string, received null``; unset means absent."""
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "data_source_url": {"type": "string"}},
        "required": ["query"],
    }
    tool = build_mcp_tool("wiki", MCPTool(name="search", description="d", input_schema=schema))
    with patch("hypergolic.mcptools.tool_bridge.execute_mcp_tool") as execute:
        execute.return_value = SimpleNamespace(is_error=False, iter_text_blocks=lambda: [])
        assert tool.run is not None
        await tool.run(cast(Any, tool.input_schema)(query="q"), cast(Any, None))
    assert execute.call_args.args[2] == {"query": "q"}
