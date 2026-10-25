"""Tests for hypergolic.sessions.transformers — pure helpers extracted from the router."""

from datetime import datetime, timezone
from types import SimpleNamespace

from hypergolic.enums import ModelTier, SessionStatus
from hypergolic.harness.primitives.approval import ToolApprovalDecision
from hypergolic.harness.primitives.results import InputSchema
from hypergolic.harness.primitives.tool import Tool
from tests._factories import policy
from hypergolic.sessions.transformers import (
    build_skill_infos,
    build_tool_info,
    session_response,
)


def _make_db_session(**overrides):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    defaults = dict(
        id="sess-1",
        model_tier=ModelTier.MEDIUM,
        project_id="proj-1",
        role="generalist",
        status=SessionStatus.IDLE,
        created_at=now,
        updated_at=now,
        parent_id=None,
        description=None,
        conclusion_rating=None,
        conclusion_feedback=None,
        concluded_at=None,
        worktree_path=None,
        worktree_branch=None,
        base_branch=None,
        worktree_status=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


async def _noop_run(ctx):
    return "ok"


async def _noop_run_with_input(inp, ctx):
    return "ok"


def _tool(
    *,
    id: str = "t",
    name: str = "T",
    description: str = "d",
    run=_noop_run,
    approval="ALLOW",
    input_schema=None,
) -> Tool:
    return Tool(
        id=id, name=name, description=description,
        run=run, approval=policy(approval), input_schema=input_schema,
    )


# --- session_response ---


def test_session_response_basic():
    row = _make_db_session()
    resp = session_response(row, "My Project")
    assert resp.id == "sess-1"
    assert resp.project_name == "My Project"
    assert resp.model_tier == ModelTier.MEDIUM
    assert resp.role == "generalist"
    assert resp.status == SessionStatus.IDLE
    assert resp.message_count == 0
    assert resp.workflow_id is None
    assert resp.workflow_name is None
    assert resp.parent_id is None
    assert resp.concluded_at is None


def test_session_response_with_workflow():
    row = _make_db_session()
    resp = session_response(
        row, "P",
        message_count=5,
        workflow_id="wf-1",
        workflow_state_id="state-a",
        workflow_name="My Workflow",
        workflow_state_name="Draft",
    )
    assert resp.message_count == 5
    assert resp.workflow_id == "wf-1"
    assert resp.workflow_state_id == "state-a"
    assert resp.workflow_name == "My Workflow"
    assert resp.workflow_state_name == "Draft"


def test_session_response_with_conclusion():
    concluded = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    row = _make_db_session(
        description="test desc",
        conclusion_rating=4,
        conclusion_feedback="good",
        concluded_at=concluded,
    )
    resp = session_response(row, "P")
    assert resp.description == "test desc"
    assert resp.conclusion_rating == 4
    assert resp.conclusion_feedback == "good"
    assert resp.concluded_at is not None


# --- build_tool_info ---


def test_build_tool_info_basic():
    info = build_tool_info(_tool(id="my_tool", name="My Tool", description="Does stuff"), "base")
    assert info.id == "my_tool"
    assert info.name == "My Tool"
    assert info.description == "Does stuff"
    assert info.reason == "base"
    assert info.requires_approval is False
    assert info.mcp_server is None
    assert info.input_schema == {"type": "object", "properties": {}}
    assert info.token_estimate > 0


def test_build_tool_info_prices_the_input_schema():
    class MyInput(InputSchema):
        x: int

    schemaless = build_tool_info(_tool(), "base")
    with_schema = build_tool_info(
        _tool(run=_noop_run_with_input, input_schema=MyInput), "base"
    )
    assert with_schema.input_schema is not None
    assert "x" in with_schema.input_schema["properties"]
    assert with_schema.token_estimate > schemaless.token_estimate


def test_build_tool_info_gated_tool():
    assert build_tool_info(_tool(approval="REQUIRE_APPROVAL"), "base").requires_approval is True


def test_build_tool_info_per_argument_policy_reports_as_gated():
    """A policy that needs its arguments has no posture to report, so fail closed."""
    def per_argument(ctx):
        return ToolApprovalDecision(decision="REQUIRE_APPROVAL" if ctx.input.x else "ALLOW")

    tool = _tool(approval=per_argument)
    assert build_tool_info(tool, "base").requires_approval is True


# --- build_skill_infos ---


def test_build_skill_infos_empty():
    assert build_skill_infos([]) == []


def test_build_skill_infos_maps_fields():
    skills = [
        {"id": "s1", "name": "Skill 1", "description": "d1", "source": "base"},
        {"id": "s2", "name": "Skill 2", "description": "d2", "source": "user"},
    ]
    result = build_skill_infos(skills)
    assert [(s.id, s.name, s.description, s.source) for s in result] == [
        ("s1", "Skill 1", "d1", "base"),
        ("s2", "Skill 2", "d2", "user"),
    ]
