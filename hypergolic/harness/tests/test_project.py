"""Tests for hypergolic.harness.project."""

import pytest
from pydantic import ValidationError

from hypergolic.harness.primitives.tool import Tool
from hypergolic.harness.project import Project
from tests._factories import build_skill as _skill, build_workflow as _workflow
from hypergolic.sandbox.model.sandbox import DEFAULT_SANDBOX_ID
from hypergolic.sandbox.model.sandbox import ProjectSandbox
from hypergolic.sandbox.model.containers import Container
from unittest.mock import patch


async def _noop(inp, ctx):
    return "ok"


def _tool(tid: str = "t1") -> Tool:
    return Tool(id=tid, name=tid, description="d", run=_noop)


def test_project_minimal_construction():
    p = Project(id="p1", name="P1", description="desc", git_root="/tmp")
    assert p.id == "p1"
    assert p.name == "P1"
    assert p.description == "desc"
    assert p.git_root == "/tmp"
    assert p.prompt_path is None
    assert p.prompt is None
    assert p.prompt_fn is None
    assert p.tools == []
    assert p.skills == []
    assert p.workflows == []


def test_project_with_prompt():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp", prompt="Hello")
    assert p.prompt == "Hello"


def test_project_with_prompt_path():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp", prompt_path="/some/path.md")
    assert p.prompt_path == "/some/path.md"


def test_project_with_prompt_fn():
    def fn(app): return "dynamic"
    p = Project(id="p1", name="P1", description="d", git_root="/tmp", prompt_fn=fn)
    assert p.prompt_fn is fn


def test_project_prompt_exclusivity_raises():
    with pytest.raises(ValidationError):
        Project(id="p1", name="P1", description="d", git_root="/tmp", prompt="inline", prompt_path="/some/path.md")


def test_project_prompt_fn_and_prompt_raises():
    with pytest.raises(ValidationError):
        Project(id="p1", name="P1", description="d", git_root="/tmp", prompt="inline", prompt_fn=lambda app: "fn")


def test_register_tool():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    p.register_tool(_tool("t1"))
    assert len(p.tools) == 1
    assert p.tools[0].id == "t1"


def test_register_tools():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    p.register_tools([_tool("t1"), _tool("t2")])
    assert len(p.tools) == 2


def test_register_skill():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    p.register_skill(_skill("s1"))
    assert len(p.skills) == 1
    assert p.skills[0].id == "s1"


def test_register_skills():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    p.register_skills([_skill("s1"), _skill("s2")])
    assert len(p.skills) == 2


def test_register_workflow():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    p.register_workflow(_workflow("wf1"))
    assert len(p.workflows) == 1
    assert p.workflows[0].id == "wf1"


def test_register_workflows():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    p.register_workflows([_workflow("wf1"), _workflow("wf2")])
    assert len(p.workflows) == 2


def test_project_with_initial_tools():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp", tools=[_tool("t1")])
    assert len(p.tools) == 1


def test_project_with_initial_skills():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp", skills=[_skill("s1")])
    assert len(p.skills) == 1


def test_project_with_initial_workflows():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp", workflows=[_workflow("wf1")])
    assert len(p.workflows) == 1


def test_configure_sandbox_has_no_filesystem_side_effect(tmp_path):

    sandbox = ProjectSandbox(id="proj-eager", containers=[Container(id="only", image="alpine")])
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        p.configure_sandbox(sandbox)

    assert p.sandbox is sandbox
    assert any(t.id == "cmd" for t in p.tools)
    assert list(tmp_path.iterdir()) == []


def test_configure_sandbox_rejects_second_sandbox(tmp_path):

    sandbox = ProjectSandbox(id="proj-eager", containers=[Container(id="only", image="alpine")])
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        p.configure_sandbox(sandbox)
        with pytest.raises(ValueError, match="already has a sandbox"):
            p.configure_sandbox(sandbox)


def test_configure_sandbox_rejects_reserved_default_id():
    sandbox = ProjectSandbox(
        id=DEFAULT_SANDBOX_ID, containers=[Container(id="only", image="alpine")]
    )
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    with pytest.raises(ValueError, match="reserved"):
        p.configure_sandbox(sandbox)


def test_unconfigured_project_resolves_to_default_sandbox():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    resolved = p.resolved_sandbox
    assert resolved is not None
    assert resolved.id == DEFAULT_SANDBOX_ID
    # Memoized: same instance on repeat access (no per-turn re-allocation).
    assert p.resolved_sandbox is resolved


def test_opted_out_project_has_no_sandbox():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    p.configure_sandbox(None)
    assert p.resolved_sandbox is None


def test_default_cmd_tool_memoized():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    first = p.default_cmd_tool()
    assert first is not None
    assert first.id == "cmd"
    # Same instance on repeat access — the per-turn build path does no work
    # after the first call.
    assert p.default_cmd_tool() is first


def test_default_cmd_tool_none_when_configured(tmp_path):

    sandbox = ProjectSandbox(id="proj-x", containers=[Container(id="only", image="alpine")])
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        p.configure_sandbox(sandbox)
    assert p.default_cmd_tool() is None


def test_default_cmd_tool_none_when_opted_out():
    p = Project(id="p1", name="P1", description="d", git_root="/tmp")
    p.configure_sandbox(None)
    assert p.default_cmd_tool() is None
