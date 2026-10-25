"""Tests for JSON-schema transforms in ``hypergolic.tools.json_schema``."""

from typing import Optional

from pydantic import BaseModel, Field

from hypergolic.tools.json_schema import (
    collapse_nullable_anyof,
    drop_default_null,
    optimize_schema,
    strip_schema_noise,
)


# --- collapse_nullable_anyof ------------------------------------------------


def test_collapse_nullable_anyof_simple():
    schema = {
        "type": "object",
        "properties": {
            "max_depth": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
            }
        },
    }
    collapse_nullable_anyof(schema)
    prop = schema["properties"]["max_depth"]
    assert "anyOf" not in prop
    assert prop["type"] == ["integer", "null"]
    assert prop["default"] is None


def test_collapse_nullable_anyof_preserves_non_null_anyof():
    """anyOf with no null branch should be left alone."""
    schema = {
        "type": "object",
        "properties": {
            "x": {"anyOf": [{"type": "integer"}, {"type": "string"}]}
        },
    }
    before = {"anyOf": [{"type": "integer"}, {"type": "string"}]}
    collapse_nullable_anyof(schema)
    assert schema["properties"]["x"] == before


def test_collapse_nullable_anyof_preserves_complex_branch():
    """anyOf where a branch has more than just a ``type`` key should be left alone."""
    schema = {
        "type": "object",
        "properties": {
            "xs": {
                "anyOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "null"},
                ],
            }
        },
    }
    before = dict(schema["properties"]["xs"])
    collapse_nullable_anyof(schema)
    assert schema["properties"]["xs"] == before


def test_collapse_nullable_anyof_recurses_into_nested():
    schema = {
        "type": "object",
        "properties": {
            "outer": {
                "type": "object",
                "properties": {
                    "inner": {"anyOf": [{"type": "string"}, {"type": "null"}]}
                },
            }
        },
    }
    collapse_nullable_anyof(schema)
    inner = schema["properties"]["outer"]["properties"]["inner"]
    assert inner["type"] == ["string", "null"]
    assert "anyOf" not in inner


# --- drop_default_null ------------------------------------------------------


def test_drop_default_null_on_nullable_type_list():
    """After collapse, ``type: [T, null]`` makes ``default: null`` redundant."""
    schema = {
        "type": "object",
        "properties": {
            "x": {"type": ["integer", "null"], "default": None}
        },
    }
    drop_default_null(schema)
    assert "default" not in schema["properties"]["x"]


def test_drop_default_null_on_anyof_null():
    """Pre-collapse shape: anyOf with null branch is also nullable."""
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
            }
        },
    }
    drop_default_null(schema)
    assert "default" not in schema["properties"]["x"]


def test_drop_default_null_preserves_non_null_defaults():
    """A real default (e.g. 0, False, '') must be preserved."""
    schema = {
        "type": "object",
        "properties": {
            "a": {"type": ["integer", "null"], "default": 0},
            "b": {"type": "boolean", "default": False},
        },
    }
    drop_default_null(schema)
    assert schema["properties"]["a"]["default"] == 0
    assert schema["properties"]["b"]["default"] is False


def test_drop_default_null_keeps_default_on_non_nullable():
    """``default: null`` on a non-nullable field is weird but keep it."""
    schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "default": None},
        },
    }
    drop_default_null(schema)
    assert schema["properties"]["x"]["default"] is None


# --- optimize_schema (end to end) -------------------------------------------


def test_optimize_schema_on_pydantic_optional_field():
    """Real Pydantic output for Optional[int] with default None gets fully minified."""

    class MyInput(BaseModel):
        name: str
        max_depth: Optional[int] = None
        pattern: Optional[str] = Field(default=None, description="Glob pattern")

    schema = MyInput.model_json_schema()
    optimize_schema(schema)

    assert "title" not in schema
    assert "additionalProperties" not in schema

    max_depth = schema["properties"]["max_depth"]
    assert max_depth["type"] == ["integer", "null"]
    assert "anyOf" not in max_depth
    assert "default" not in max_depth
    assert "title" not in max_depth

    pattern = schema["properties"]["pattern"]
    assert pattern["type"] == ["string", "null"]
    assert "anyOf" not in pattern
    assert "default" not in pattern
    assert pattern["description"] == "Glob pattern"


def test_optimize_schema_resolves_refs():
    """``$ref`` fields are inlined and ``$defs`` dropped."""
    schema = {
        "$defs": {"MyEnum": {"enum": ["a", "b"], "type": "string"}},
        "properties": {"x": {"$ref": "#/$defs/MyEnum"}},
        "type": "object",
    }
    optimize_schema(schema)
    assert "$defs" not in schema
    assert schema["properties"]["x"] == {"enum": ["a", "b"], "type": "string"}


def test_strip_schema_noise_keeps_typed_map_additional_properties():
    schema = {
        "type": "object",
        "properties": {
            "env": {"type": "object", "additionalProperties": {"type": "string"}},
        },
        "additionalProperties": False,
    }
    strip_schema_noise(schema)
    assert "additionalProperties" not in schema
    assert schema["properties"]["env"]["additionalProperties"] == {"type": "string"}


def test_strip_schema_noise_keeps_field_named_title():
    """A property *named* ``title`` is data, not schema noise (pull_request regression)."""
    schema = {
        "type": "object",
        "title": "PublishPrInput",
        "properties": {
            "title": {"type": "string", "title": "Title"},
            "body": {"type": "string", "title": "Body"},
        },
        "required": ["title", "body"],
    }
    strip_schema_noise(schema)
    assert "title" not in schema
    assert schema["properties"]["title"] == {"type": "string"}
    assert schema["properties"]["body"] == {"type": "string"}


def test_strip_schema_noise_drops_empty_description():
    schema = {
        "type": "object",
        "properties": {
            "branch": {"type": "string", "description": ""},
            "base": {"type": "string", "description": "PR target"},
        },
    }
    strip_schema_noise(schema)
    assert "description" not in schema["properties"]["branch"]
    assert schema["properties"]["base"]["description"] == "PR target"
