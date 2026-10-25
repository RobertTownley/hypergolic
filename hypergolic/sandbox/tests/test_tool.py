from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hypergolic.sandbox.model.containers import Container
from hypergolic.sandbox.model.egress import Egress
from hypergolic.sandbox.model.sandbox import ProjectSandbox
from hypergolic.sandbox.tool import make_project_sandbox_tool, write_compose
from hypergolic.sandbox.manager.provisioning import _config_hash
from hypergolic.sandbox.manager.types import ExecResult, SandboxError, SandboxUnavailableError
from hypergolic.harness.primitives.tool import Tool, ToolContext
from tests._factories import build_session
from tests.conftest import make_project, make_session


def _sandbox(tmp_path, **kw):
    return ProjectSandbox(
        id="t1",
        containers=[Container(id="dev", image="ubuntu")],
        egress=Egress.DenyAll(),
        **kw,
    )


@pytest.fixture
def sandbox_env(tmp_path, broadcast, monkeypatch):
    monkeypatch.setattr(
        "hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path
    )
    make_project("p1")
    sid = make_session(project_id="p1")

    def make(tool_id: str = "cmd", **sandbox_kw):
        session = build_session(sid=sid, project_id="p1", project_path="/tmp/p1")
        ctx = ToolContext(session=session, broadcast=broadcast, tool_id=tool_id)
        tool = make_project_sandbox_tool(_sandbox(tmp_path, **sandbox_kw))
        return ctx, tool, tool.input_schema

    return make


def test_make_project_sandbox_tool_returns_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path
    )
    tool = make_project_sandbox_tool(_sandbox(tmp_path))
    assert isinstance(tool, Tool)
    assert tool.id == "cmd"


async def test_run_starts_sandbox_then_executes(sandbox_env):
    ctx, tool, Input = sandbox_env()
    exec_result = ExecResult(stdout="hello", stderr="", returncode=0)
    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", AsyncMock(return_value="hg-cmd-abc")),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", AsyncMock(return_value=exec_result)),
    ):
        result = await tool.run(Input(command="echo hello"), ctx)
    assert not result.is_error
    assert "hello" in result.content[0]["text"]


async def test_run_skips_start_when_already_running(sandbox_env, tmp_path):
    ctx, tool, Input = sandbox_env()
    mock_sandbox = MagicMock()
    mock_sandbox.status = "running"
    mock_sandbox.config_hash = _config_hash(write_compose(_sandbox(tmp_path)))
    mock_start = AsyncMock()
    with (
        patch("hypergolic.sandbox.manager.sandbox_rows.get", return_value=mock_sandbox),
        patch("hypergolic.sandbox.tool.exec.start_sandbox", mock_start),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox",
              AsyncMock(return_value=ExecResult(stdout="file.txt", stderr="", returncode=0))),
    ):
        result = await tool.run(Input(command="ls"), ctx)
    mock_start.assert_not_called()
    assert not result.is_error


@pytest.mark.parametrize("error, expected", [
    (SandboxUnavailableError("Docker not found"), "Docker not found"),
    (SandboxError("Container failed"), "Sandbox startup failed"),
])
async def test_run_start_failures(sandbox_env, error, expected):
    ctx, tool, Input = sandbox_env()
    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", AsyncMock(side_effect=error)),
    ):
        result = await tool.run(Input(command="ls"), ctx)
    assert result.is_error
    assert expected in result.content[0]["text"]


async def test_run_nonzero_exit_is_failure(sandbox_env):
    ctx, tool, Input = sandbox_env()
    exec_result = ExecResult(stdout="", stderr="error output", returncode=1)
    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", AsyncMock()),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", AsyncMock(return_value=exec_result)),
    ):
        result = await tool.run(Input(command="exit 1"), ctx)
    assert result.is_error
    assert "[exit 1]" in result.content[0]["text"]


async def test_run_exec_sandbox_error(sandbox_env):
    ctx, tool, Input = sandbox_env()
    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", AsyncMock()),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", AsyncMock(side_effect=SandboxError("container died"))),
    ):
        result = await tool.run(Input(command="ls"), ctx)
    assert result.is_error
    assert "Sandbox error" in result.content[0]["text"]


async def test_run_includes_stdout_and_stderr(sandbox_env):
    ctx, tool, Input = sandbox_env()
    exec_result = ExecResult(stdout="output line", stderr="warning", returncode=0)
    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", AsyncMock()),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", AsyncMock(return_value=exec_result)),
    ):
        result = await tool.run(Input(command="cmd"), ctx)
    text = result.content[0]["text"]
    assert text == "output line\nwarning"


async def test_run_clean_success_is_raw_stdout(sandbox_env):
    ctx, tool, Input = sandbox_env()
    exec_result = ExecResult(stdout="output line", stderr="", returncode=0)
    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", AsyncMock()),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", AsyncMock(return_value=exec_result)),
    ):
        result = await tool.run(Input(command="cmd"), ctx)
    assert result.content[0]["text"] == "output line"


@pytest.mark.parametrize("env_value, expected", [(None, 120), ("45", 45)])
async def test_run_timeout_from_env(sandbox_env, monkeypatch, env_value, expected):
    if env_value is None:
        monkeypatch.delenv("HYPERGOLIC_DEFAULT_COMMAND_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("HYPERGOLIC_DEFAULT_COMMAND_TIMEOUT", env_value)
    ctx, tool, Input = sandbox_env()
    mock_exec = AsyncMock(return_value=ExecResult(stdout="", stderr="", returncode=0))
    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", AsyncMock()),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", mock_exec),
    ):
        await tool.run(Input(command="ls"), ctx)
    assert mock_exec.call_args[1]["timeout"] == expected


async def test_run_timeout_from_sandbox_model_overrides_env(sandbox_env, monkeypatch):
    monkeypatch.setenv("HYPERGOLIC_DEFAULT_COMMAND_TIMEOUT", "45")
    ctx, tool, Input = sandbox_env(command_timeout=300)
    mock_exec = AsyncMock(return_value=ExecResult(stdout="", stderr="", returncode=0))
    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", AsyncMock()),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", mock_exec),
    ):
        await tool.run(Input(command="ls"), ctx)
    assert mock_exec.call_args[1]["timeout"] == 300


def test_command_timeout_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        _sandbox(tmp_path, command_timeout=0)
