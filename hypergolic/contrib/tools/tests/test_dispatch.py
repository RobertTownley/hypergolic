"""Tests for the unified dispatch tool."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from hypergolic.contrib.tools.dispatch import (
    ASYNC_DISPATCH_PROMPT,
    DISPATCH_PROMPT,
    _render_file_reference,
    build_dispatch_tool,
)
from hypergolic.dispatch.state import DispatchResult
from hypergolic.enums import ModelTier
from hypergolic.harness.primitives.results import InputSchema
from hypergolic.harness.primitives.tool import Tool, ToolContext
from tests._factories import build_session


def _input_schema(tool: Tool) -> type[InputSchema]:
    schema = tool.input_schema
    assert schema is not None and issubclass(schema, InputSchema)
    return schema


def _make_input(tool: Tool, **kwargs: Any) -> InputSchema:
    schema = _input_schema(tool)
    return schema(**kwargs)


def _session(tmp_path, role: str = "generalist"):
    return build_session(project_path=str(tmp_path), worktree_path=str(tmp_path), role=role)


def _ctx(tmp_path, broadcast: AsyncMock | None = None) -> ToolContext:
    return ToolContext(
        session=_session(tmp_path),
        broadcast=broadcast or AsyncMock(),
        tool_id="dispatch",
    )


# ── build_dispatch_tool ───────────────────────────────────────────────────────


def test_build_dispatch_tool_empty_role_list_returns_none():
    assert build_dispatch_tool([]) is None


def test_build_dispatch_tool_has_expected_metadata():
    tool = build_dispatch_tool(["researcher"])
    assert tool is not None
    assert tool.id == "dispatch"
    assert tool.name == "Dispatch"
    assert tool.description.strip()


def test_dispatch_input_role_is_enum():
    tool = build_dispatch_tool(["researcher", "reviewer"])
    assert tool is not None
    schema = _input_schema(tool).model_json_schema()
    assert "role" in schema["properties"]


# ── _render_file_reference ────────────────────────────────────────────────────


def test_render_file_reference_no_read_capability(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("secret")
    text = _render_file_reference("a.txt", _session(tmp_path, "researcher"), False)
    assert "cannot read files" in text
    assert "secret" not in text


def test_render_file_reference_outside_project_requires_approval(tmp_path):
    # path that won't be in the project or readonly allowlist
    outside = "/etc/passwd"
    text = _render_file_reference(
        outside, _session(tmp_path, "researcher"), True
    )
    assert "not permitted" in text


def test_render_file_reference_allowed_inlines_contents(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("hello world")
    text = _render_file_reference(
        "note.md", _session(tmp_path, "researcher"), True
    )
    assert "hello world" in text
    assert "note.md" in text


def test_render_file_reference_missing_file(tmp_path):
    text = _render_file_reference(
        "missing.txt", _session(tmp_path, "researcher"), True
    )
    assert "file not found" in text


def test_render_file_reference_directory(tmp_path):
    (tmp_path / "d").mkdir()
    text = _render_file_reference(
        "d", _session(tmp_path, "researcher"), True
    )
    assert "not a file" in text


def test_render_file_reference_binary(tmp_path):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\xff\xfe\x00\x01")
    text = _render_file_reference(
        "bin.dat", _session(tmp_path, "researcher"), True
    )
    assert "UTF-8" in text


# ── run_dispatch integration ──────────────────────────────────────────────────


def _get_run(tool):
    # harness Tool has `.run`
    return tool.run


async def test_run_dispatch_forwards_to_dispatch_runner(tmp_path):
    tool = build_dispatch_tool(["researcher"])
    assert tool is not None
    ctx = _ctx(tmp_path)
    inp = _make_input(tool, role="researcher", prompt="do the thing")

    with patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=DispatchResult(outcome="success", conclusion="ok")),
    ) as mock_dispatch:
        result = await _get_run(tool)(inp, ctx)

    assert not result.is_error
    call_kwargs = mock_dispatch.call_args[1]
    assert call_kwargs["role"] == "researcher"
    assert call_kwargs["dispatch_prompt"] == DISPATCH_PROMPT
    # The first content block is the prompt
    assert call_kwargs["content_blocks"][0]["text"] == "do the thing"
    # No file references → no second block
    assert len(call_kwargs["content_blocks"]) == 1


async def test_run_dispatch_attaches_file_references(tmp_path):
    (tmp_path / "ctx.txt").write_text("reference content")
    tool = build_dispatch_tool(["researcher"])
    assert tool is not None
    ctx = _ctx(tmp_path)
    inp = _make_input(
        tool, role="researcher", prompt="task", file_references=["ctx.txt"]
    )

    with patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=DispatchResult(outcome="success", conclusion="done")),
    ) as mock_dispatch:
        await _get_run(tool)(inp, ctx)

    blocks = mock_dispatch.call_args[1]["content_blocks"]
    assert len(blocks) == 2
    assert "reference content" in blocks[1]["text"]
    assert "ctx.txt" in blocks[1]["text"]


async def test_run_dispatch_marks_unreadable_files(tmp_path):
    tool = build_dispatch_tool(["reviewer"], receiver_can_read_files=False)
    assert tool is not None
    ctx = _ctx(tmp_path)
    inp = _make_input(
        tool,
        role="reviewer",
        prompt="please review",
        file_references=["secret.txt"],
    )

    with patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=DispatchResult(outcome="success", conclusion="ok")),
    ) as mock_dispatch:
        await _get_run(tool)(inp, ctx)

    blocks = mock_dispatch.call_args[1]["content_blocks"]
    # Second block is the attached references with a "not provided" marker
    assert "not provided" in blocks[1]["text"]
    assert "cannot read files" in blocks[1]["text"]


async def test_run_dispatch_failure_outcome(tmp_path):
    tool = build_dispatch_tool(["researcher"])
    assert tool is not None
    ctx = _ctx(tmp_path)
    inp = _make_input(tool, role="researcher", prompt="task")

    with patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=DispatchResult(outcome="failure", conclusion="nope")),
    ):
        result = await _get_run(tool)(inp, ctx)

    assert result.is_error
    assert "Dispatch failed" in result.content[0]["text"]
    assert "nope" in result.content[0]["text"]


async def test_run_dispatch_suppressed_outcome(tmp_path):
    tool = build_dispatch_tool(["researcher"])
    assert tool is not None
    ctx = _ctx(tmp_path)
    inp = _make_input(tool, role="researcher", prompt="task")

    with patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=DispatchResult(outcome="suppressed", conclusion="interrupted")),
    ):
        result = await _get_run(tool)(inp, ctx)

    assert result.is_error
    assert "interrupted" in result.content[0]["text"].lower()


async def test_run_dispatch_default_tier_is_none(tmp_path):
    """Without an explicit tier the engine inherits the parent session's."""
    tool = build_dispatch_tool(["worker"])
    assert tool is not None
    ctx = _ctx(tmp_path)
    inp = _make_input(tool, role="worker", prompt="task")

    with patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=DispatchResult(outcome="success", conclusion="ok")),
    ) as mock_dispatch:
        await _get_run(tool)(inp, ctx)

    assert mock_dispatch.call_args[1]["model_tier"] is None


async def test_run_dispatch_forwards_explicit_tier(tmp_path):
    tool = build_dispatch_tool(["worker"])
    assert tool is not None
    ctx = _ctx(tmp_path)
    inp = _make_input(tool, role="worker", prompt="task", model_tier=ModelTier.HIGH)

    with patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=DispatchResult(outcome="success", conclusion="ok")),
    ) as mock_dispatch:
        await _get_run(tool)(inp, ctx)

    assert mock_dispatch.call_args[1]["model_tier"] is ModelTier.HIGH


def test_dispatch_role_enum_excludes_invalid_values():
    tool = build_dispatch_tool(["researcher"])
    assert tool is not None
    with pytest.raises(ValidationError):
        _make_input(tool, role="generalist", prompt="x")


# ── child / wait / pins ───────────────────────────────────────────────────────


def _tool() -> Tool:
    tool = build_dispatch_tool(["researcher"])
    assert tool is not None
    return tool


def _patched_dispatch(result=None):
    return patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=result or DispatchResult(outcome="success", conclusion="ok")),
    )


async def test_child_defaults_to_generalist(tmp_path):
    tool = _tool()
    with _patched_dispatch() as mock_dispatch:
        result = await _get_run(tool)(_make_input(tool, prompt="x"), _ctx(tmp_path))
    assert not result.is_error
    kw = mock_dispatch.call_args[1]
    assert kw["role"] == "generalist" and kw["child"] is True


async def test_child_in_another_project_forwards_project_and_base(tmp_path):
    tool = _tool()
    inp = _make_input(tool, role="researcher", prompt="x", project="other", base="release")
    with _patched_dispatch() as mock_dispatch:
        result = await _get_run(tool)(inp, _ctx(tmp_path))
    assert not result.is_error
    kw = mock_dispatch.call_args[1]
    assert kw["child"] is True and kw["project_id"] == "other" and kw["base"] == "release"


async def test_base_and_app_pin_are_exclusive(tmp_path):
    tool = _tool()
    inp = _make_input(tool, prompt="x", base="main", pins={"app": "abc123"})
    result = await _get_run(tool)(inp, _ctx(tmp_path))
    assert result.is_error and "base" in result.content[0]["text"]


async def test_standalone_defaults_role_and_drops_dispatch_prompt(tmp_path):
    tool = _tool()
    inp = _make_input(tool, prompt="x", child=False, project="other")
    with _patched_dispatch() as mock_dispatch:
        await _get_run(tool)(inp, _ctx(tmp_path))
    kw = mock_dispatch.call_args[1]
    assert kw["role"] == "generalist"
    assert kw["dispatch_prompt"] is None
    assert kw["child"] is False and kw["project_id"] == "other"


async def test_conducted_child_defaults_to_generalist_without_rules_prompt(tmp_path):
    tool = _tool()
    inp = _make_input(tool, prompt="x", conduct=True)
    with _patched_dispatch() as mock_dispatch:
        result = await _get_run(tool)(inp, _ctx(tmp_path))
    assert not result.is_error
    kw = mock_dispatch.call_args[1]
    assert kw["role"] == "generalist"
    assert kw["dispatch_prompt"] is None
    assert kw["child"] is True and kw["conducted"] is True


async def test_no_wait_uses_async_prompt_and_reports_start(tmp_path):
    tool = _tool()
    inp = _make_input(tool, role="researcher", prompt="x", wait=False)
    started = DispatchResult(outcome="started", conclusion="", child_session_id="C1", worktree_branch="b")
    with _patched_dispatch(started) as mock_dispatch:
        result = await _get_run(tool)(inp, _ctx(tmp_path))
    assert mock_dispatch.call_args[1]["dispatch_prompt"] == ASYNC_DISPATCH_PROMPT
    assert mock_dispatch.call_args[1]["wait"] is False
    assert not result.is_error and "C1" in result.content[0]["text"]


# ── dispatch --conclude ─────────────────────────────────────────────────────────


def _child(parent_id: str | None = "s-1"):
    return build_session("c-1", parent_id=parent_id)


async def _conclude(child, *, pending: bool = False, keep_branch: bool = False):
    tool = build_dispatch_tool(["researcher"])
    assert tool is not None
    inp = _make_input(tool, conclude="c-1", keep_branch=keep_branch)
    pending_map = {"c-1": object()} if pending else {}
    with patch("hypergolic.sessions.operations.load_session", return_value=child), patch(
        "hypergolic.dispatch.state._pending_dispatches", pending_map,
    ), patch("hypergolic.dispatch.child_end.end_child", new=AsyncMock()) as end:
        result = await _get_run(tool)(inp, _ctx("/tmp/p"))
    return result, end


async def test_dispatch_conclude_ends_an_idle_child_of_mine():
    result, end = await _conclude(_child(), keep_branch=True)
    assert not result.is_error
    end.assert_awaited_once()
    assert end.call_args.args[0] == "c-1"
    assert end.call_args.kwargs == {"keep_branch": True}


async def test_dispatch_conclude_refuses_another_sessions_child():
    result, end = await _conclude(_child(parent_id="someone-else"))
    assert result.is_error
    end.assert_not_awaited()


async def test_dispatch_conclude_refuses_a_running_child():
    result, end = await _conclude(_child(), pending=True)
    assert result.is_error and "still running" in result.content[0]["text"]
    end.assert_not_awaited()
