"""The JSON tool schemas a turn ships to the model.

Exactly one tool goes over the wire, so this is a formality rather than a
subsystem: the schema is shaped once per turn from the session's containers and
never changes as capability does. Commands are discovered from ``/tools`` on
``PATH`` instead.
"""

from __future__ import annotations

from typing import cast

from anthropic.types import ToolUnionParam

from hypergolic.harness.primitives.tool import Tool
from hypergolic.tools.json_schema import optimize_schema


def wire_schema(tool: Tool) -> ToolUnionParam:
    if tool.input_schema is not None:
        schema = tool.input_schema.model_json_schema()
        optimize_schema(schema)
    else:
        schema = {"type": "object", "properties": {}}
    param: dict = {"name": tool.id, "input_schema": schema}
    if tool.description:
        param["description"] = tool.description
    return cast(ToolUnionParam, param)


def wire_schemas(tools: list[Tool]) -> list[ToolUnionParam]:
    return [wire_schema(t) for t in tools]
