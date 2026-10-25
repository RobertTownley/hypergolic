from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from hypergolic.db.models import DBToolApproval
from hypergolic.harness.primitives.approval import ToolApprovalDecision
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool
from hypergolic.ids import new_id
from hypergolic.tools.approval import (
    _CHILD_APPROVAL_DENIAL,
    _CLI_APPROVAL_DENIAL,
    AnnotationItem,
    ApprovalResponse,
    build_resolved_view,
    resolve_approval_decision,
    resolve_mcp_policy,
)
from hypergolic.tools.approval_outcome import append_annotations, format_denial, record_approval
from hypergolic.tools.approval_view import ApprovalView, CodeBlock
from tests._factories import build_session as _session
from tests.conftest import make_project, make_session
from tests.helpers.blocks import text_at


class _DummyInput(BaseModel):
    x: int = 1


async def _noop(inp, ctx):
    return ToolResult(content=[])


def _tool(**kwargs: Any) -> Tool:
    if "requires_approval" in kwargs:
        kwargs["approval"] = "REQUIRE_APPROVAL" if kwargs.pop("requires_approval") else "ALLOW"
    if "call_tool" in kwargs:
        kwargs["run"] = kwargs.pop("call_tool")
    defaults: dict[str, Any] = dict(
        id="t1", name="Test", description="d", input_schema=_DummyInput, run=_noop,
    )
    defaults.update(kwargs)
    return Tool(**defaults)


_GET_APP = "hypergolic.tools.approval.get_app"


def _app_with_policy(policy) -> MagicMock:
    app = MagicMock()
    app.mcp_approval_policy = policy
    return app


@pytest.mark.parametrize("approval", ["ALLOW", "DENY", "REQUIRE_APPROVAL"])
def test_resolve_decision_tool_approval(approval):
    decision = resolve_approval_decision(
        _tool(approval=approval), {}, _session(),
    )
    assert decision.decision == approval


def test_mcp_policy_allows():
    app = _app_with_policy(lambda ctx: ToolApprovalDecision(decision="ALLOW"))
    with patch(_GET_APP, return_value=app):
        decision = resolve_mcp_policy("wiki", "search", {"query": "hello"}, _session())
    assert decision.decision == "ALLOW"


@pytest.mark.parametrize(
    "get_app_kwargs",
    [
        dict(side_effect=RuntimeError("no app")),
        dict(return_value=_app_with_policy(None)),
        dict(return_value=_app_with_policy(MagicMock(side_effect=ValueError("boom")))),
    ],
)
def test_mcp_policy_falls_back_to_require_approval(get_app_kwargs):
    with patch(_GET_APP, **get_app_kwargs):
        decision = resolve_mcp_policy("wiki", "search", {}, _session())
    assert decision.decision == "REQUIRE_APPROVAL"


@pytest.mark.parametrize(
    "tool_kwargs",
    [dict(requires_approval=True), dict(approval="REQUIRE_APPROVAL")],
)
def test_child_session_require_approval_becomes_deny(tool_kwargs):
    decision = resolve_approval_decision(
        _tool(**tool_kwargs), {}, _session(parent_id="parent-1"),
    )
    assert decision.decision == "DENY"
    assert decision.reason == _CHILD_APPROVAL_DENIAL


def test_child_with_a_waiting_parent_delegates():
    with patch(
        "hypergolic.tools.approval_delegate.can_delegate", return_value=True
    ):
        decision = resolve_approval_decision(
            _tool(requires_approval=True), {}, _session(parent_id="parent-1"),
        )
    assert decision.decision == "DELEGATE"


def test_explicit_deny_is_never_delegated():
    with patch(
        "hypergolic.tools.approval_delegate.can_delegate", return_value=True
    ):
        decision = resolve_approval_decision(
            _tool(approval="DENY"), {}, _session(parent_id="parent-1"),
        )
    assert decision.decision == "DENY"


def test_cli_session_require_approval_becomes_deny():
    decision = resolve_approval_decision(
        _tool(approval="REQUIRE_APPROVAL"), {}, _session(origin="cli"),
    )
    assert decision.decision == "DENY"
    assert decision.reason == _CLI_APPROVAL_DENIAL


def test_cli_session_allow_still_allows():
    decision = resolve_approval_decision(
        _tool(approval="ALLOW"), {}, _session(origin="cli"),
    )
    assert decision.decision == "ALLOW"


def test_child_session_allow_is_unaffected():
    decision = resolve_approval_decision(
        _tool(requires_approval=False), {},
        _session(parent_id="parent-1"),
    )
    assert decision.decision == "ALLOW"


def test_adult_session_still_requires_approval():
    decision = resolve_approval_decision(
        _tool(requires_approval=True), {},
        _session(parent_id=None),
    )
    assert decision.decision == "REQUIRE_APPROVAL"


def test_build_resolved_view_no_view():
    assert build_resolved_view(_tool(approval_view=None), {}) is None


def test_build_resolved_view_with_view():
    view = ApprovalView(blocks=[CodeBlock(field="cmd", language="bash")])
    resolved = build_resolved_view(_tool(approval_view=view), {"cmd": "ls"})
    assert resolved is not None
    assert resolved.blocks[0]["value"] == "ls"
    assert resolved.blocks[0]["language"] == "bash"
    assert resolved.show_raw_json is True


def test_format_denial_simple():
    assert format_denial(ApprovalResponse(approved=False)) == "User denied tool call."


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        (dict(denial_reason="not needed"), ["Reason: not needed"]),
        (dict(annotations=[AnnotationItem(highlighted_text="foo", comment="bar")]),
         ['"foo"', "bar", "annotations"]),
        (dict(denial_reason="wrong",
              annotations=[AnnotationItem(highlighted_text="x", comment="y")]),
         ["Reason: wrong", '"x": y']),
    ],
)
def test_format_denial_details(kwargs, expected):
    text = format_denial(ApprovalResponse(approved=False, **kwargs))
    for fragment in expected:
        assert fragment in text


def test_append_annotations():
    output = ToolResult(content=[{"type": "text", "text": "result"}])
    ann = [AnnotationItem(highlighted_text="code", comment="fix this")]
    result = append_annotations(output, ann)
    assert len(result.content) == 2
    assert "fix this" in text_at(result.content, 1)
    assert result.is_error is False


def test_append_annotations_preserves_flags():
    output = ToolResult(content=[{"type": "text", "text": "r"}], is_error=True)
    result = append_annotations(output, [AnnotationItem(highlighted_text="a", comment="b")])
    assert result.is_error is True


@pytest.mark.parametrize(
    "tool_name, tool_input, response, expected_reason",
    [
        ("write", {"files": [{"path": "a.py", "content": "x"}]},
         ApprovalResponse(approved=True), None),
        ("command", {"command": "rm -rf /"},
         ApprovalResponse(approved=False, denial_reason="too risky",
                          annotations=[AnnotationItem(highlighted_text="a.py:3", comment="fix")]),
         "too risky"),
    ],
)
def test_record_approval_persists(tool_name, tool_input, response, expected_reason, audit_rows):
    make_project("p-1")
    session_id = make_session(project_id="p-1")
    tool_use_id = new_id()

    record_approval(
        session_id=session_id,
        tool_use_id=tool_use_id,
        tool_name=tool_name,
        tool_input=tool_input,
        response=response,
    )

    [row] = audit_rows.of(DBToolApproval)
    assert (row.session_id, row.tool_use_id) == (session_id, tool_use_id)
    assert row.tool_name == tool_name
    assert row.approved is response.approved
    assert row.denial_reason == expected_reason
    expected_ann = [
        {"highlighted_text": a.highlighted_text, "comment": a.comment}
        for a in response.annotations
    ] if response.annotations else None
    assert row.annotations == expected_ann


def test_record_approval_db_error_is_swallowed():
    with patch("hypergolic.db.audit_rows.insert", side_effect=RuntimeError("db gone")):
        record_approval(
            session_id="s-1",
            tool_use_id="tu-1",
            tool_name="t",
            tool_input={},
            response=ApprovalResponse(approved=True),
        )
