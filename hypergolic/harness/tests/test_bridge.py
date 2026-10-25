"""Tests for hypergolic.harness.bridge."""

from unittest.mock import AsyncMock

from hypergolic.schemas import Session
from hypergolic.harness.bridge import evaluate_harness_approval, invoke_tool, run_tool_call_validation
from hypergolic.harness.primitives.validation import ValidationOutcome, ValidationResult
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from tests._factories import build_session, policy


async def _noop_run(ctx):
    return ToolResult.text("ok")


async def _noop_run_with_input(inp, ctx):
    return ToolResult.text("ok")


def _session(**overrides) -> Session:
    return build_session(sid="sess-1", project_path="/tmp/testproject", **overrides)


def _make_session() -> Session:
    return build_session(sid="s-1", project_id="p-1")


class SampleInput(InputSchema):
    path: str


def _tool(*, approval="ALLOW", input_schema=None, run=_noop_run, tid="t") -> Tool:
    return Tool(
        id=tid,
        name="T",
        description="d",
        run=run,
        approval=policy(approval),
        input_schema=input_schema,
    )


def _ctx(tool_id: str = "test-tool") -> ToolContext:
    return ToolContext(session=_make_session(), broadcast=AsyncMock(), tool_id=tool_id)

# --- evaluate_harness_approval ---------------------------------------------


def test_string_allow():
    assert evaluate_harness_approval(_tool(approval="ALLOW"), {}).decision == "ALLOW"


def test_string_deny():
    assert evaluate_harness_approval(_tool(approval="DENY"), {}).decision == "DENY"


def test_string_require():
    assert evaluate_harness_approval(_tool(approval="REQUIRE_APPROVAL"), {}).decision == "REQUIRE_APPROVAL"


def test_string_unknown_defaults_require():
    assert evaluate_harness_approval(_tool(approval="SOMETHING_ELSE"), {}).decision == "REQUIRE_APPROVAL"


def test_callable_receives_approval_context():
    received = {}

    def approve(ctx: ApprovalContext) -> ToolApprovalDecision:
        received["path"] = ctx.input.path
        received["project"] = ctx.session.project_path
        return ToolApprovalDecision(decision="ALLOW")

    tool = _tool(approval=approve, input_schema=SampleInput, run=_noop_run_with_input)
    result = evaluate_harness_approval(tool, {"path": "/foo"}, _session())
    assert result.decision == "ALLOW"
    assert received == {"path": "/foo", "project": "/tmp/testproject"}


def test_callable_no_input_schema_passes_none():
    received = {}

    def approve(ctx: ApprovalContext) -> ToolApprovalDecision:
        received["input"] = ctx.input
        return ToolApprovalDecision(decision="ALLOW")

    assert evaluate_harness_approval(_tool(approval=approve), {}, _session()).decision == "ALLOW"
    assert received["input"] is None


def test_callable_no_session():
    received = {}

    def approve(ctx: ApprovalContext) -> ToolApprovalDecision:
        received["session"] = ctx.session
        return ToolApprovalDecision(decision="REQUIRE_APPROVAL")

    tool = _tool(approval=approve, input_schema=SampleInput, run=_noop_run_with_input)
    assert evaluate_harness_approval(tool, {"path": "/foo"}, session=None).decision == "REQUIRE_APPROVAL"
    assert received["session"] is None


def test_callable_exception_defaults_require():
    def approve(ctx: ApprovalContext) -> ToolApprovalDecision:
        raise RuntimeError("boom")

    tool = _tool(approval=approve, input_schema=SampleInput, run=_noop_run_with_input)
    assert evaluate_harness_approval(tool, {"path": "/foo"}, _session()).decision == "REQUIRE_APPROVAL"


# --- invoke_tool ------------------------------------------------------------


async def test_invoke_tool_with_input():
    async def run(inp: SampleInput, ctx: ToolContext) -> ToolResult:
        return ToolResult.text(inp.path)

    out = await invoke_tool(_tool(run=run, input_schema=SampleInput), SampleInput(path="hello"), _ctx())
    assert out.is_error is False
    assert out.first_text() == "hello"


async def test_invoke_tool_without_input():
    out = await invoke_tool(_tool(run=_noop_run), None, _ctx())
    assert out.is_error is False
    assert out.first_text() == "ok"


async def test_invoke_tool_failure():
    async def run(ctx: ToolContext) -> ToolResult:
        return ToolResult.text("fail", is_error=True)

    out = await invoke_tool(_tool(run=run), None, _ctx())
    assert out.is_error is True


async def test_invoke_tool_exception_returns_error():
    async def run(ctx: ToolContext) -> ToolResult:
        raise RuntimeError("exploded")

    out = await invoke_tool(_tool(run=run), None, _ctx())
    assert out.is_error is True
    assert "exploded" in out.first_text()


async def test_invoke_tool_passes_context():
    received = {}

    async def run(ctx: ToolContext) -> ToolResult:
        received["session"] = ctx.session
        received["tool_id"] = ctx.tool_id
        return ToolResult(content=[])

    session = _make_session()
    ctx = ToolContext(session=session, broadcast=AsyncMock(), tool_id="my-tool")
    await invoke_tool(_tool(run=run, tid="my-tool"), None, ctx)
    assert received["session"] is session
    assert received["tool_id"] == "my-tool"


# --- ToolContext.sandbox_id -------------------------------------------------


def test_sandbox_id_no_qualifier_returns_tool_id():
    assert _ctx("python_lab").sandbox_id() == "python_lab"


def test_sandbox_id_with_qualifier():
    assert _ctx("python_lab").sandbox_id("uv") == "python_lab_uv"


async def test_validation_defaults_to_valid():
    assert (await run_tool_call_validation(_tool(), None, _ctx())) == ValidationResult.valid()


async def test_validation_returns_result():
    async def check(inp, ctx):
        return ValidationResult.invalid("nope")
    tool = _tool().model_copy(update={"validate_tool_call": check})
    assert (await run_tool_call_validation(tool, None, _ctx())).message == "nope"


async def test_validation_reports_exception():
    async def check(inp, ctx):
        raise RuntimeError("boom")
    tool = _tool().model_copy(update={"validate_tool_call": check})
    result = await run_tool_call_validation(tool, None, _ctx())
    assert not result.is_valid and "boom" in (result.message or "")


async def test_validation_rejects_wrong_return_type():
    async def check(inp, ctx):
        return "nope"
    tool = _tool().model_copy(update={"validate_tool_call": check})
    assert not (await run_tool_call_validation(tool, None, _ctx())).is_valid


def test_invalid_needs_message():
    import pytest
    with pytest.raises(ValueError):
        ValidationResult(outcome=ValidationOutcome.INVALID)


def test_sync_validate_rejected():
    import pytest
    with pytest.raises(ValueError, match="validate_tool_call function must be async"):
        Tool(id="t", name="T", description="d", validate_tool_call=lambda i, c: None)
