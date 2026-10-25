"""The `mcp` command's contract: a server's tools are read at call time, so
nothing about enabling one touches the tool schemas the model was sent."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hypergolic.commands.parsers import UsageError
from hypergolic.config.schemas import MCPServerConfig
from hypergolic.contrib.tools.mcp_command.actions import approve_mcp, run_mcp
from hypergolic.contrib.tools.mcp_command.command import mcp_command
from hypergolic.contrib.tools.mcp_command.parse import McpInput, _align_to_schema, parse_mcp
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.tool import ToolContext
from tests._factories import build_session
from hypergolic.commands.docs import approval_label
import anyio


@pytest.fixture
def ctx(broadcast) -> ToolContext:
    return ToolContext(session=build_session(), broadcast=broadcast, tool_id="mcp")


def _tool(name: str, schema: dict | None = None):
    return SimpleNamespace(name=name, description="d", input_schema=schema or {})


def _server(*tools, name="a"):
    return SimpleNamespace(
        name=name, project_path=None, toolsets=set(), tools=list(tools), tools_changed=asyncio.Event()
    )


def _manager(available=None, connected=None, result=None):
    manager = MagicMock()
    manager.refresh_tools = AsyncMock()
    manager.get_available_servers.return_value = available or {}
    manager.is_connected.side_effect = lambda name: name in (connected or {})
    manager.get_connected_server.side_effect = lambda name: (connected or {}).get(name)
    manager.call_tool = AsyncMock(return_value=result or {"content": []})
    manager.connect = AsyncMock(side_effect=lambda name, _path=None: (connected or {})[name])
    manager.disconnect = AsyncMock()
    return manager


def _patches(manager, enabled=frozenset()):
    return (
        patch("hypergolic.mcptools.client.manager.get_mcp_manager", return_value=manager),
        patch("hypergolic.contrib.tools.mcp_command.actions.get_enabled_servers", return_value=set(enabled)),
        patch("hypergolic.contrib.tools.mcp_command.actions.set_enabled_servers"),
        patch("hypergolic.contrib.tools.mcp_command.catalog.refresh_tools"),
        patch("hypergolic.contrib.tools.mcp_command.actions.TOOL_LIST_SETTLE_S", 0.01),
    )


async def _run(inp: McpInput, ctx, manager, enabled=frozenset()):
    p1, p2, p3, p4, p5 = _patches(manager, enabled)
    with p1, p2, p3, p4, p5:
        return await run_mcp(inp, ctx)


def test_flags_keep_the_spelling_and_the_text_they_were_given():
    parsed = parse_mcp(["exec", "analytics", "query_chart", "--chart-id=abc", "--limit=5"])
    assert parsed.action == "exec"
    assert parsed.arguments == {"chart-id": "abc", "limit": "5"}
    assert parsed.literal == ["chart-id", "limit"]


def test_a_separated_flag_value_and_a_bare_flag_both_parse():
    parsed = parse_mcp(["exec", "s", "t", "--name", "x", "--verbose"])
    assert parsed.arguments == {"name": "x", "verbose": True}


def test_a_json_object_is_the_escape_hatch_for_a_nested_schema():
    parsed = parse_mcp(["exec", "s", "t", '{"filter": {"country": "US"}}'])
    assert parsed.arguments == {"filter": {"country": "US"}}
    assert parsed.literal == []


def test_flags_win_over_a_json_object_in_any_order():
    parsed = parse_mcp(["exec", "s", "t", "--note=flag", '{"note": "json", "n": 1}'])
    assert parsed.arguments == {"note": "flag", "n": 1}
    assert parsed.literal == ["note"]


def test_double_dash_ends_flags():
    parsed = parse_mcp(["exec", "s", "t", "--a=1", "--", '{"b": 2}'])
    assert parsed.arguments == {"a": "1", "b": 2}


def test_the_escape_hatch_keeps_the_types_the_caller_wrote():
    """Its values are already JSON, so retyping them would undo the one route
    that can say `"5"` and mean the string."""
    parsed = parse_mcp(["exec", "s", "t", '{"note": "5"}'])
    assert _align_to_schema(parsed.arguments, {}, parsed.literal) == {"note": "5"}


def test_subcommands_report_their_own_usage_errors():
    with pytest.raises(UsageError, match="subcommand"):
        parse_mcp([])
    with pytest.raises(UsageError, match="unknown subcommand"):
        parse_mcp(["enable", "analytics"])
    with pytest.raises(UsageError, match="no arguments"):
        parse_mcp(["list", "analytics"])
    with pytest.raises(UsageError, match="server and a tool"):
        parse_mcp(["schema", "analytics"])
    with pytest.raises(UsageError, match="then arguments"):
        parse_mcp(["exec", "analytics"])


def _approve(action: Any, **fields: Any) -> ToolApprovalDecision:
    inp = McpInput(action=action, **fields)
    return approve_mcp(
        ApprovalContext(input=inp, session=build_session())
    )


def test_reading_what_exists_is_auto_approved():
    assert _approve("list").decision == "ALLOW"
    assert _approve("schema", server="a", tool="t").decision == "ALLOW"
    assert _approve("deactivate", server="a").decision == "ALLOW"


def test_connecting_to_a_server_is_gated_because_it_may_open_a_browser():
    decision = _approve("activate", server="analytics")
    assert decision.decision == "REQUIRE_APPROVAL"
    assert "OAuth" in (decision.reason or "")


def test_a_call_defers_to_the_harness_mcp_policy():
    with patch(
        "hypergolic.contrib.tools.mcp_command.actions.resolve_mcp_policy",
        return_value=ToolApprovalDecision(decision="ALLOW"),
    ) as policy:
        assert _approve("exec", server="analytics", tool="query_chart").decision == "ALLOW"
    assert policy.call_args[0][:2] == ("analytics", "query_chart")


def test_a_policy_that_needs_arguments_cannot_be_summarized_in_the_readme():
    assert "read `source`" in approval_label(mcp_command)


async def test_list_reports_status_and_tool_names_as_json(ctx):
    manager = _manager(
        available={"analytics": (MCPServerConfig(description="Product analytics"), "project")},
        connected={"analytics": _server(_tool("query_chart"))},
    )
    result = await _run(McpInput(action="list"), ctx, manager, enabled={"analytics"})
    rows = json.loads(result.stdout)
    assert rows == [
        {
            "server": "analytics",
            "description": "Product analytics",
            "source": "project",
            "status": "active",
            "tools": ["query_chart"],
        }
    ]
    assert result.exit_code == 0


async def test_list_says_so_when_nothing_is_configured(ctx):
    result = await _run(McpInput(action="list"), ctx, _manager())
    assert "No MCP servers" in result.stdout


async def test_activating_regenerates_tools_so_the_shell_sees_it_immediately(ctx):
    manager = _manager(connected={"analytics": _server(_tool("query_chart"))})
    p1, p2, p3, p4, _ = _patches(manager)
    with p1, p2, p3 as set_enabled, p4 as refresh:
        result = await run_mcp(McpInput(action="activate", server="analytics"), ctx)
    assert result.exit_code == 0
    assert "query_chart" in result.stdout
    assert set_enabled.call_args[0][1] == {"analytics"}
    refresh.assert_called_once()


async def test_a_failed_connection_is_a_nonzero_exit_not_an_exception(ctx):
    manager = _manager()
    manager.connect = AsyncMock(side_effect=RuntimeError("no such server"))
    result = await _run(McpInput(action="activate", server="nope"), ctx, manager)
    assert result.exit_code != 0
    assert "no such server" in result.stderr


async def test_schema_prints_what_the_agent_must_satisfy(ctx):
    schema = {"type": "object", "properties": {"chart_id": {"type": "string"}}}
    manager = _manager(connected={"a": _server(_tool("query_chart", schema))})
    result = await _run(McpInput(action="schema", server="a", tool="query_chart"), ctx, manager)
    assert json.loads(result.stdout) == schema


async def test_an_unconnected_server_says_how_to_fix_it(ctx):
    result = await _run(McpInput(action="schema", server="a", tool="t"), ctx, _manager())
    assert "mcp activate a" in result.stderr


async def test_an_unknown_tool_lists_the_ones_that_exist(ctx):
    manager = _manager(connected={"a": _server(_tool("query_chart"))})
    result = await _run(McpInput(action="schema", server="a", tool="nope"), ctx, manager)
    assert "query_chart" in result.stderr


async def test_an_unknown_tool_refreshes_the_cache_before_giving_up(ctx):
    server = _server(_tool("old"))
    manager = _manager(connected={"a": server}, result={"content": [{"type": "text", "text": "ok"}]})
    manager.refresh_tools.side_effect = lambda _name: server.tools.append(_tool("new"))
    result = await _run(McpInput(action="exec", server="a", tool="new"), ctx, manager)
    assert result.stdout == "ok\n"
    manager.refresh_tools.assert_awaited_once_with("a")


async def test_exec_reports_a_tool_list_change_the_server_announced(ctx):
    server = _server(_tool("toggle"))
    manager = _manager(connected={"a": server}, result={"content": [{"type": "text", "text": "done"}]})

    async def call(*_args):
        server.tools_changed.set()
        return {"content": [{"type": "text", "text": "done"}]}

    manager.call_tool = AsyncMock(side_effect=call)
    manager.refresh_tools.side_effect = lambda _name: server.tools.append(_tool("added"))
    result = await _run(McpInput(action="exec", server="a", tool="toggle"), ctx, manager)
    assert result.stdout == "done\nTool list changed. Tools: toggle, added\n"


async def test_exec_passes_validated_arguments_and_returns_text(ctx):
    manager = _manager(
        connected={"a": _server(_tool("query_chart"))},
        result={"content": [{"type": "text", "text": "42"}]},
    )
    inp = McpInput(action="exec", server="a", tool="query_chart", arguments={"chart_id": "x"})
    result = await _run(inp, ctx, manager)
    assert result.stdout == "42\n"
    assert manager.call_tool.await_args[0] == ("a", "query_chart", {"chart_id": "x"})


async def test_a_tool_error_becomes_a_nonzero_exit(ctx):
    manager = _manager(
        connected={"a": _server(_tool("t"))},
        result={"content": [{"type": "text", "text": "bad request"}], "is_error": True},
    )
    result = await _run(McpInput(action="exec", server="a", tool="t"), ctx, manager)
    assert result.exit_code != 0
    assert "bad request" in result.stderr


@pytest.mark.parametrize(
    "given,properties,expected",
    [
        ({"chart-id": 1}, {"chart_id": {}}, {"chart_id": 1}),
        ({"issue_tracker": True}, {"issue-tracker": {}}, {"issue-tracker": True}),
        ({"metrics": True}, {"metrics": {}}, {"metrics": True}),
        ({"mystery": 1}, {"chart_id": {}}, {"mystery": 1}),
        ({"chart-id": 1}, {}, {"chart-id": 1}),
    ],
    ids=["dash-to-snake", "snake-to-dash", "exact", "unknown-passes-through", "no-schema"],
)
def test_the_published_schema_decides_how_a_flag_is_spelled(given, properties, expected):
    schema = {"type": "object", "properties": properties} if properties else {}
    assert _align_to_schema(given, schema) == expected


@pytest.mark.parametrize(
    "given,properties,expected",
    [
        ({"ts": "1700000000.000100"}, {"ts": {"type": "string"}}, {"ts": "1700000000.000100"}),
        ({"limit": "5"}, {"limit": {"type": "integer"}}, {"limit": 5}),
        ({"limit": "5"}, {}, {"limit": 5}),
        ({"ids": "[1,2]"}, {"ids": {"type": "array"}}, {"ids": [1, 2]}),
        ({"name": "abc"}, {"name": {"type": "integer"}}, {"name": "abc"}),
        ({"ts": "1700000000.000100"}, {"ts": {"type": ["string", "null"]}}, {"ts": "1700000000.000100"}),
        (
            {"ts": "1700000000.000100"},
            {"ts": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
            {"ts": "1700000000.000100"},
        ),
        (
            {"ids": '["a","b"]'},
            {"ids": {"anyOf": [{"type": "array"}, {"type": "string"}]}},
            {"ids": ["a", "b"]},
        ),
        ({"flag": True}, {"flag": {"type": "string"}}, {"flag": True}),
    ],
    ids=[
        "string-keeps-its-digits",
        "integer-parses",
        "untyped-falls-back-to-json",
        "array-parses",
        "unparseable-stays-text",
        "nullable-string-keeps-its-digits",
        "anyOf-string-keeps-its-digits",
        "string-or-array-still-parses",
        "non-text-passes-through",
    ],
)
def test_the_published_schema_decides_how_a_flag_is_typed(given, properties, expected):
    schema = {"type": "object", "properties": properties} if properties else {}
    assert _align_to_schema(given, schema) == expected


async def test_exec_sends_a_string_timestamp_as_text(ctx):
    schema = {
        "type": "object",
        "properties": {"reply_ts": {"type": "string"}, "message": {"type": "string"}},
    }
    manager = _manager(connected={"g": _server(_tool("send", schema))})
    inp = parse_mcp(
        ["exec", "g", "send", "--reply_ts=1700000000.000100", "--message=hi"]
    )
    await _run(inp, ctx, manager)
    assert manager.call_tool.await_args.args[2] == {
        "reply_ts": "1700000000.000100",
        "message": "hi",
    }


async def test_exec_spells_arguments_the_way_the_server_declared_them(ctx):
    """The gateway names its servers with dashes; guessing at parse time
    silently sent `issue_tracker` and the enable was a no-op."""
    schema = {"type": "object", "properties": {"issue-tracker": {"type": "boolean"}}}
    manager = _manager(connected={"g": _server(_tool("configure", schema))})
    inp = McpInput(action="exec", server="g", tool="configure", arguments={"issue_tracker": True})

    await _run(inp, ctx, manager)

    assert manager.call_tool.await_args[0] == ("g", "configure", {"issue-tracker": True})


async def test_a_dead_transport_reports_itself_instead_of_looking_empty(ctx):
    """The failure mode this exists for: `ClosedResourceError` stringifies to
    nothing, so a broken session read as a call that returned no output."""

    manager = _manager(connected={"g": _server(_tool("t"))})
    manager.call_tool = AsyncMock(side_effect=anyio.ClosedResourceError)

    result = await _run(McpInput(action="exec", server="g", tool="t"), ctx, manager)

    assert result.exit_code != 0
    assert "transport is closed" in result.stderr


async def test_deactivating_the_last_holder_closes_the_connection(ctx):
    """`mcp deactivate X && mcp activate X` has to be able to replace a session
    that has gone bad, which means deactivate must reach the transport."""
    manager = _manager(connected={"g": _server(_tool("t"))})
    with patch("hypergolic.contrib.tools.mcp_command.actions.sessions_using", return_value=set()):
        result = await _run(McpInput(action="deactivate", server="g"), ctx, manager, enabled={"g"})

    assert "deactivated 'g'" in result.stdout
    manager.disconnect.assert_awaited_once_with("g")


async def test_another_session_still_using_a_server_keeps_it_connected(ctx):
    manager = _manager(connected={"g": _server(_tool("t"))})
    with patch("hypergolic.contrib.tools.mcp_command.actions.sessions_using", return_value={"other"}):
        await _run(McpInput(action="deactivate", server="g"), ctx, manager, enabled={"g"})

    manager.disconnect.assert_not_awaited()


def test_the_policy_judges_the_arguments_the_server_will_receive():
    """Aligning after the approval decision would let a policy inspect
    `force_push` while the wire carried `force-push`."""
    schema = {"type": "object", "properties": {"force-push": {"type": "boolean"}}}
    manager = _manager(connected={"g": _server(_tool("run", schema))})
    inp = McpInput(action="exec", server="g", tool="run", arguments={"force_push": True})

    with patch("hypergolic.mcptools.client.manager.get_mcp_manager", return_value=manager):
        with patch(
            "hypergolic.contrib.tools.mcp_command.actions.resolve_mcp_policy",
            return_value=ToolApprovalDecision(decision="ALLOW"),
        ) as policy:
            approve_mcp(ApprovalContext(input=inp, session=build_session()))

    assert policy.call_args[0][2] == {"force-push": True}
    assert inp.arguments == {"force_push": True}, "deciding must not rewrite the invocation"


def test_alignment_at_approval_time_survives_an_unconnected_server():
    manager = _manager()
    inp = McpInput(action="exec", server="g", tool="run", arguments={"a": 1})

    with patch("hypergolic.mcptools.client.manager.get_mcp_manager", return_value=manager):
        with patch(
            "hypergolic.contrib.tools.mcp_command.actions.resolve_mcp_policy",
            return_value=ToolApprovalDecision(decision="ALLOW"),
        ) as policy:
            approve_mcp(ApprovalContext(input=inp, session=build_session()))

    assert policy.call_args[0][2] == {"a": 1}


_SWITCH = "set-toolsets"
_SWITCH_SCHEMA = {"properties": {"chat": {"type": "boolean"}, "metrics": {"type": "boolean"}}}


def _gateway(*tools):
    server = _server(_tool(_SWITCH, _SWITCH_SCHEMA), *tools, name="g")
    available = {"g": (MCPServerConfig(toolset_switch=_SWITCH), "user")}
    manager = _manager(available=available, connected={"g": server})
    allow = patch(
        "hypergolic.contrib.tools.mcp_command.catalog.resolve_mcp_policy",
        return_value=ToolApprovalDecision(decision="ALLOW"),
    )
    return server, manager, allow


async def test_a_hidden_toolset_is_enabled_without_dropping_the_ones_in_use(ctx):
    server, manager, allow = _gateway(_tool("chat__read"))
    manager.refresh_tools.side_effect = lambda _name: (
        server.tools.append(_tool("metrics__run-query"))
        if manager.call_tool.await_count else None
    )
    with allow:
        inp = McpInput(action="exec", server="g", tool="metrics__run-query")
        await _run(inp, ctx, manager)
    switch_call, dql_call = manager.call_tool.await_args_list
    assert switch_call[0] == ("g", _SWITCH, {"chat": True, "metrics": True})
    assert dql_call[0][1] == "metrics__run-query"


async def test_an_agent_switch_call_keeps_toolsets_another_session_enabled(ctx):
    server, manager, _allow = _gateway()
    server.toolsets = {"metrics"}
    await _run(McpInput(action="exec", server="g", tool=_SWITCH, arguments={"chat": True}), ctx, manager)
    assert manager.call_tool.await_args[0][2] == {"metrics": True, "chat": True}
    assert server.toolsets == {"metrics", "chat"}


async def test_an_explicit_disable_still_wins(ctx):
    server, manager, _allow = _gateway(_tool("chat__read"))
    inp = McpInput(action="exec", server="g", tool=_SWITCH, arguments={"chat": False})
    await _run(inp, ctx, manager)
    assert manager.call_tool.await_args[0][2] == {"chat": False}
    assert server.toolsets == set()


async def test_without_a_declared_switch_a_missing_tool_is_only_reported(ctx):
    manager = _manager(connected={"a": _server(_tool(_SWITCH))})
    result = await _run(McpInput(action="exec", server="a", tool="chat__read"), ctx, manager)
    assert "has no tool 'chat__read'" in result.stderr
    manager.call_tool.assert_not_awaited()
