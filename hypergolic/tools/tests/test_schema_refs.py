"""Tests for $ref resolution in tool schemas."""

from enum import Enum
from typing import Any, cast

from pydantic import BaseModel

from hypergolic.tools.json_schema import resolve_refs, strip_schema_noise
from hypergolic.tools.wire import wire_schema
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.harness.primitives.results import ToolResult


def test_resolve_refs_inlines_enum():
    """$ref to an enum in $defs should be inlined."""
    schema = {
        "$defs": {
            "SkillIdEnum": {
                "enum": ["harness-engineer", "prompt-engineer"],
                "type": "string",
            }
        },
        "properties": {
            "skill_ids": {
                "items": {"$ref": "#/$defs/SkillIdEnum"},
                "type": "array",
            }
        },
        "required": ["skill_ids"],
        "type": "object",
    }
    resolve_refs(schema)
    assert "$defs" not in schema
    items = schema["properties"]["skill_ids"]["items"]
    assert items == {"enum": ["harness-engineer", "prompt-engineer"], "type": "string"}


def test_resolve_refs_no_defs():
    """When there are no $defs, schema is unchanged."""
    schema = {
        "properties": {"name": {"type": "string"}},
        "type": "object",
    }
    original = dict(schema)
    resolve_refs(schema)
    assert schema == original


def test_resolve_refs_nested():
    """$ref inside anyOf should also be resolved."""
    schema = {
        "$defs": {
            "MyEnum": {"enum": ["a", "b"], "type": "string"}
        },
        "properties": {
            "value": {
                "anyOf": [
                    {"$ref": "#/$defs/MyEnum"},
                    {"type": "null"},
                ],
            }
        },
        "type": "object",
    }
    resolve_refs(schema)
    assert "$defs" not in schema
    any_of = schema["properties"]["value"]["anyOf"]
    assert any_of[0] == {"enum": ["a", "b"], "type": "string"}
    assert any_of[1] == {"type": "null"}


def test_strip_schema_noise_resolves_refs():
    """strip_schema_noise should resolve $ref before stripping."""
    schema = {
        "$defs": {
            "ColorEnum": {"enum": ["red", "blue"], "title": "ColorEnum", "type": "string"}
        },
        "properties": {
            "colors": {
                "items": {"$ref": "#/$defs/ColorEnum"},
                "title": "Colors",
                "type": "array",
            }
        },
        "required": ["colors"],
        "title": "MyModel",
        "type": "object",
    }
    strip_schema_noise(schema)
    assert "$defs" not in schema
    assert "title" not in schema
    assert "additionalProperties" not in schema
    items = schema["properties"]["colors"]["items"]
    assert items["enum"] == ["red", "blue"]
    assert items["type"] == "string"
    assert "title" not in items


def test_wire_schema_with_enum_field():
    """The wire schema inlines enum $refs from Pydantic models."""

    MyEnum = Enum("MyEnum", {"alpha": "alpha", "beta": "beta"}, type=str)

    class MyInput(BaseModel):
        items: list[MyEnum]  # type: ignore[valid-type]

    async def noop(inp: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult()

    tool = Tool(
        id="test",
        name="Test",
        description="test",
        input_schema=MyInput,
        run=noop,
    )
    param = wire_schema(tool)
    schema: dict[str, Any] = cast(dict[str, Any], param)["input_schema"]
    assert "$defs" not in schema
    items_schema = schema["properties"]["items"]["items"]
    assert "enum" in items_schema
    assert sorted(items_schema["enum"]) == ["alpha", "beta"]
