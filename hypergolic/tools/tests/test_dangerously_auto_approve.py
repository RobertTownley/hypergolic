"""Tests for HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE (trusted-host autonomy mode).

The flag has four effects, each covered here:
  - every REQUIRE_APPROVAL decision resolves to ALLOW (children included)
  - the sandbox shell is replaced by the host shell, and sandboxes refuse to start
  - `host_cmd` goes too: the host shell already ships as `cmd`
"""

from typing import Any

import pytest
from unittest.mock import patch
from pydantic import BaseModel

from hypergolic.config.settings import Settings, settings
from hypergolic.contrib.roles.registry import ALL_CONTRIB_ROLES
from hypergolic.contrib.tools.command import dangerous_command_tool
from hypergolic.contrib.skills.registry import ALL_CONTRIB_SKILLS
from hypergolic.contrib.tools.registry import UNIVERSAL_TOOLS
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool
from hypergolic.harness.project import Project
from hypergolic.sandbox.manager.start import start_sandbox
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.commands.registry import sandbox_shell
from hypergolic.tools.approval import resolve_approval_decision
from tests._factories import build_session, commands_for
from hypergolic.prompts.builder import _sandbox_context_lines


@pytest.fixture
def dangerous(monkeypatch):
    monkeypatch.setattr(settings, "HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE", True)


def test_setting_defaults_off():
    with patch.dict("os.environ", {}, clear=True):
        assert Settings().HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE is False


# ── approval resolution ──────────────────────────────────────────


class _DummyInput(BaseModel):
    x: int = 1


async def _noop(inp, ctx):
    return ToolResult(content=[])


def _tool(**kwargs: Any) -> Tool:
    defaults: dict[str, Any] = dict(
        id="t1", name="Test", description="d", input_schema=_DummyInput, run=_noop,
    )
    defaults.update(kwargs)
    return Tool(**defaults)


@pytest.mark.parametrize("parent_id", [None, "parent-1"])
def test_require_approval_downgrades_to_allow(dangerous, parent_id):
    decision = resolve_approval_decision(
        _tool(approval="REQUIRE_APPROVAL"), {},
        build_session("s1", parent_id=parent_id),
    )
    assert decision.decision == "ALLOW"


def test_deny_still_stands(dangerous):
    decision = resolve_approval_decision(
        _tool(approval="DENY"), {}, build_session("s1"),
    )
    assert decision.decision == "DENY"


# ── the command set and the shell ────────────────────────────────


def _make_app() -> App:
    app = App()
    app.register_tools(list(UNIVERSAL_TOOLS))
    app.register_roles(ALL_CONTRIB_ROLES)
    app.register_skills(ALL_CONTRIB_SKILLS)
    app.register_project(
        Project(id="p1", name="P1", description="d", git_root="/tmp/test")
    )
    set_app(app)
    return app


def _session(role: str = "generalist", **kwargs):
    return build_session("s1", project_id="p1", project_path="/tmp/test", role=role, **kwargs)


def test_the_shell_is_the_host_shell_without_a_description(dangerous):
    _make_app()
    shell = sandbox_shell(_session())
    assert shell is not None
    assert shell.id == "cmd"
    assert shell.description == ""
    assert shell.run is dangerous_command_tool.run


def test_children_lose_host_cmd_but_keep_the_shell(dangerous):
    _make_app()
    for role in ("worker", "researcher", "reviewer"):
        commands = commands_for(_session(role, parent_id="parent-1"))
        assert "host_cmd" not in commands, role
        shell = sandbox_shell(_session(role, parent_id="parent-1"))
        assert shell is not None and shell.run is dangerous_command_tool.run, role


def test_flag_off_keeps_the_sandbox_shell_and_the_git_command():
    _make_app()
    shell = sandbox_shell(_session())
    assert shell is not None
    assert shell.run is not dangerous_command_tool.run
    commands = commands_for(_session())
    assert "host_cmd" in commands


# ── sandbox lifecycle ────────────────────────────────────────────


async def test_start_sandbox_refuses(dangerous):
    with pytest.raises(SandboxError, match="DANGEROUSLY_AUTO_APPROVE"):
        await start_sandbox(
            session_id="s1", tool_id="cmd",
            config_path="/nonexistent.yaml", project_root="/tmp",
        )


# ── prompt context ───────────────────────────────────────────────


def test_sandbox_context_replaced_with_host_notice(dangerous):
    _make_app()
    session = build_session("s1", project_id="p1", project_path="/tmp/test")
    lines = _sandbox_context_lines(session)
    assert len(lines) == 1
    assert "no sandbox" in lines[0]
