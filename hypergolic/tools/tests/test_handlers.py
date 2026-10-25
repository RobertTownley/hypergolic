import pytest
from typing import Any
from unittest.mock import AsyncMock, patch, MagicMock

from anthropic.types import ToolUseBlock, TextBlock
from pydantic import BaseModel

from hypergolic.harness.primitives.approval import ToolApprovalDecision
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.tools.approval import AnnotationItem, ApprovalResponse
from hypergolic.tools.handlers import (
    ToolUseResult,
    _execute_tool,
    _process_single_tool,
    handle_tool_use,
)
from tests._factories import build_session as _session
from tests.helpers.blocks import all_texts, first_text
from tests._factories import build_app
from hypergolic.git.worktree_lifecycle import WorktreeUnavailableError


class _DummyInput(BaseModel):
    msg: str = "hi"


async def _echo(inp, ctx):
    return ToolResult(content=[{"type": "text", "text": inp.msg}])


async def _boom(inp, ctx):
    raise RuntimeError("kaboom")


def _tool(tid: str = "t1", call_tool: Any = _echo, **kwargs: Any) -> Tool:
    if "requires_approval" in kwargs:
        kwargs["approval"] = "REQUIRE_APPROVAL" if kwargs.pop("requires_approval") else "ALLOW"
    run = kwargs.pop("call_tool", call_tool)
    defaults: dict[str, Any] = dict(
        id=tid, name="Test", description="d", input_schema=_DummyInput, run=run,
    )
    defaults.update(kwargs)
    return Tool(**defaults)


def _tool_use_block(name: str = "t1", tid: str = "tu-1", inp: dict[str, object] | None = None) -> ToolUseBlock:
    return ToolUseBlock(id=tid, type="tool_use", name=name, input=inp if inp is not None else {"msg": "hi"})


async def _noop_broadcast(event):
    pass


def _ctx(tool_id: str = "t1") -> ToolContext:
    return ToolContext(session=_session(), broadcast=_noop_broadcast, tool_id=tool_id)


async def _process(block, tools, session=None, callback=None):
    return await _process_single_tool(
        block, tools, session or _session(), _noop_broadcast, callback,
    )


@pytest.fixture(autouse=True)
def _patch_db():
    app = build_app(set_active=False)
    with patch("hypergolic.harness.app.state.get_app", return_value=app):
        yield


async def test_execute_tool_success():
    output = await _execute_tool(_tool(), _DummyInput(msg="hello"), _ctx())
    assert output.first_text() == "hello"
    assert output.is_error is False


async def test_execute_tool_exception():
    output = await _execute_tool(_tool(call_tool=_boom), _DummyInput(), _ctx())
    assert output.is_error is True
    assert "kaboom" in output.first_text()


async def test_process_tool_not_found():
    result = await _process(_tool_use_block(name="missing"), {})
    assert result["is_error"] is True
    assert "not available" in result["content"]


async def test_process_tool_allow():
    result = await _process(_tool_use_block(), {"t1": _tool()})
    assert result["is_error"] is False


async def test_process_tool_invalid_input_skips_approval():
    tool = _tool(requires_approval=True)
    block = _tool_use_block(inp={"msg": ["not", "a", "string"]})
    callback = AsyncMock(return_value=ApprovalResponse(approved=True))
    result = await _process(block, {"t1": tool}, callback=callback)
    assert result["is_error"] is True
    assert "Invalid tool input" in first_text(result["content"])
    callback.assert_not_awaited()


@pytest.mark.parametrize(
    "decision, expected",
    [
        (ToolApprovalDecision(decision="DENY", reason="Not allowed here."), "Not allowed here."),
        (ToolApprovalDecision(decision="DENY"), "denied"),
    ],
)
async def test_process_tool_deny(decision, expected):
    with patch(
        "hypergolic.tools.handlers.resolve_approval_decision", return_value=decision,
    ):
        result = await _process(_tool_use_block(), {"t1": _tool()})
    assert result["is_error"] is True
    assert expected in str(result["content"])


async def test_process_tool_approval_approved():
    callback = AsyncMock(return_value=ApprovalResponse(approved=True))
    result = await _process(
        _tool_use_block(), {"t1": _tool(requires_approval=True)}, callback=callback,
    )
    assert result["is_error"] is False
    callback.assert_awaited_once()


async def test_process_tool_approval_denied():
    callback = AsyncMock(
        return_value=ApprovalResponse(approved=False, denial_reason="nope"),
    )
    result = await _process(
        _tool_use_block(), {"t1": _tool(requires_approval=True)}, callback=callback,
    )
    assert result["is_error"] is True
    assert any("nope" in str(c) for c in result["content"])


async def test_process_tool_mocked_result_skips_the_tool():
    tool = _tool(requires_approval=True)
    callback = AsyncMock(
        return_value=ApprovalResponse(approved=False, mock_result="page ABC-1 created"),
    )
    with patch("hypergolic.tools.handlers._execute_tool", new=AsyncMock()) as execute:
        result = await _process(_tool_use_block(), {"t1": tool}, callback=callback)
    execute.assert_not_awaited()
    assert result["is_error"] is False
    assert "page ABC-1 created" in " ".join(all_texts(result["content"]))


async def test_process_tool_approval_with_annotations():
    callback = AsyncMock(
        return_value=ApprovalResponse(
            approved=True,
            annotations=[AnnotationItem(highlighted_text="line1", comment="fix")],
        ),
    )
    result = await _process(
        _tool_use_block(), {"t1": _tool(requires_approval=True)}, callback=callback,
    )
    assert result["is_error"] is False
    assert "fix" in " ".join(all_texts(result["content"]))


def _message(blocks):
    msg = MagicMock()
    msg.content = blocks
    return msg


@pytest.mark.parametrize(
    "blocks, expected_results",
    [
        ([_tool_use_block()], 1),
        ([_tool_use_block(tid="tu-1"), _tool_use_block(tid="tu-2")], 2),
        ([TextBlock(type="text", text="thinking..."), _tool_use_block()], 1),
    ],
)
async def test_handle_tool_use(blocks, expected_results):
    result = await handle_tool_use(_message(blocks), [_tool()], _session(), _noop_broadcast)
    assert isinstance(result, ToolUseResult)
    assert result.message["role"] == "user"
    content = result.message["content"]
    assert isinstance(content, list) and len(content) == expected_results


async def test_handle_annotations_skipped_on_error():
    tool = _tool(requires_approval=True, call_tool=_boom)
    callback = AsyncMock(
        return_value=ApprovalResponse(
            approved=True,
            annotations=[AnnotationItem(highlighted_text="a", comment="b")],
        ),
    )
    result = await _process(_tool_use_block(), {"t1": tool}, callback=callback)
    assert "feedback" not in " ".join(all_texts(result["content"])).lower()


@pytest.mark.parametrize(
    "response",
    [
        ApprovalResponse(approved=True),
        ApprovalResponse(approved=False, denial_reason="nope"),
    ],
)
async def test_record_approval_called_for_approval_and_denial(monkeypatch, response):
    recorded = []
    monkeypatch.setattr(
        "hypergolic.tools.handlers.record_approval",
        lambda **kwargs: recorded.append(kwargs),
    )

    callback = AsyncMock(return_value=response)
    await _process(_tool_use_block(), {"t1": _tool(requires_approval=True)}, callback=callback)

    assert len(recorded) == 1
    assert recorded[0]["tool_name"] == "t1"
    assert recorded[0]["response"].approved is response.approved
    assert recorded[0]["response"].denial_reason == response.denial_reason


def _session_with_worktree():
    return _session("s-wt", worktree_path="/tmp/wt")


async def test_process_tool_without_requires_worktree_never_waits():
    with patch(
        "hypergolic.tools.handlers.wait_for_ready", new_callable=AsyncMock,
    ) as mock_wait:
        result = await _process(
            _tool_use_block(), {"t1": _tool()}, session=_session_with_worktree(),
        )
    mock_wait.assert_not_awaited()
    assert result["is_error"] is False


async def test_process_tool_awaits_wait_for_ready_before_invoking():
    call_order: list[str] = []

    async def tracking_tool(inp, ctx):
        call_order.append("tool")
        return ToolResult(content=[{"type": "text", "text": "ok"}])

    async def tracking_wait(session_id):
        call_order.append("wait")

    tool = _tool(requires_worktree=True, call_tool=tracking_tool)
    with patch("hypergolic.tools.handlers.wait_for_ready", side_effect=tracking_wait):
        result = await _process(
            _tool_use_block(), {"t1": tool}, session=_session_with_worktree(),
        )
    assert call_order == ["wait", "tool"]
    assert result["is_error"] is False


async def test_process_tool_returns_error_on_worktree_unavailable():
    async def failing_wait(session_id):
        raise WorktreeUnavailableError("create_failed")

    async def should_not_run(inp, ctx):
        raise AssertionError("tool body should not be invoked")

    tool = _tool(requires_worktree=True, call_tool=should_not_run)
    with patch("hypergolic.tools.handlers.wait_for_ready", side_effect=failing_wait):
        result = await _process(
            _tool_use_block(), {"t1": tool}, session=_session_with_worktree(),
        )
    assert result["is_error"] is True
    text = str(result["content"])
    assert "requires a ready worktree" in text
    assert "create_failed" in text
