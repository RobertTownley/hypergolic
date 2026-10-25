"""The wire tool's schema is shaped by the session's containers."""

from unittest.mock import patch

from hypergolic.tools.cmd import build_cmd_tool
from tests._factories import build_session


def _tool_schema(containers: list[str]) -> dict:
    with patch("hypergolic.tools.cmd.shell_capable_containers", return_value=containers):
        tool = build_cmd_tool(build_session())
    assert tool.input_schema is not None
    return tool.input_schema.model_json_schema()


def test_single_container_omits_container_field():
    schema = _tool_schema(["dev"])
    assert set(schema["properties"]) == {"command"}


def test_multi_container_requires_enumerated_container():
    schema = _tool_schema(["api", "frontend"])
    assert set(schema["required"]) == {"command", "container"}
    assert schema["$defs"]["ContainerEnum"]["enum"] == ["api", "frontend"]


def test_no_sandbox_still_yields_a_usable_tool():
    schema = _tool_schema([])
    assert set(schema["properties"]) == {"command"}
