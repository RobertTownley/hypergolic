"""Tests for base/tools/command.py — run_command."""

import subprocess
from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.contrib.tools.command import (
    CommandInput,
    command_tool,
    run_command,
)
from hypergolic.harness.primitives.tool import ToolContext
from tests._factories import approval_of, build_session


@pytest.fixture
def ctx(broadcast) -> ToolContext:
    # project_path="/tmp/p" is the session's default working_directory().
    return ToolContext(session=build_session(project_path="/tmp/p"), broadcast=broadcast, tool_id="command")


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def _patch_subprocess(**kwargs):
    return patch("hypergolic.contrib.tools.command.run_subprocess", new=AsyncMock(**kwargs))


# ── Tool metadata ─────────────────────────────────────────────────────────────


def test_command_tool_metadata():
    assert command_tool.id == "host_cmd"
    # Shell commands can't be statically checked — always require approval.
    assert approval_of(command_tool) == "REQUIRE_APPROVAL"


# ── Success cases ─────────────────────────────────────────────────────────────


async def test_run_command_success_with_stdout_and_stderr(ctx):
    """stderr on a zero exit follows stdout unlabeled."""
    with _patch_subprocess(return_value=_completed(returncode=0, stdout="hello", stderr="warn")):
        result = await run_command(CommandInput(commands=["echo hello"]), ctx)
    text = result.content[0]["text"]
    assert not result.is_error
    assert text == "hello\nwarn"


async def test_run_command_clean_success_is_raw_stdout(ctx):
    with _patch_subprocess(return_value=_completed(returncode=0, stdout="hello")):
        result = await run_command(CommandInput(commands=["echo hello"]), ctx)
    assert not result.is_error
    assert result.content[0]["text"] == "hello"


async def test_run_command_no_output(ctx):
    """When stdout and stderr are both empty on success, result is just OK."""
    with _patch_subprocess(return_value=_completed(returncode=0)):
        result = await run_command(CommandInput(commands=["true"]), ctx)
    assert not result.is_error
    assert result.content[0]["text"] == "(no output)"


async def test_run_command_multiple_labels_and_joins_output(ctx):
    """Multiple commands run and their outputs are labeled per-command."""
    with _patch_subprocess(return_value=_completed(returncode=0, stdout="hi")):
        result = await run_command(CommandInput(commands=["echo a", "echo b"]), ctx)
    text = result.content[0]["text"]
    assert not result.is_error
    assert "$ echo a" in text and "$ echo b" in text


async def test_run_command_multiple_fails_if_any_fails(ctx):
    with _patch_subprocess(return_value=_completed(returncode=1, stderr="boom")):
        result = await run_command(CommandInput(commands=["a", "b"]), ctx)
    assert result.is_error


async def test_run_command_rejects_empty_commands():
    with pytest.raises(Exception):
        CommandInput(commands=[])


# ── Failure cases ─────────────────────────────────────────────────────────────


async def test_run_command_nonzero_exit_code(ctx):
    with _patch_subprocess(return_value=_completed(returncode=1, stderr="error message")):
        result = await run_command(CommandInput(commands=["false"]), ctx)
    assert result.is_error
    assert "[exit 1]" in result.content[0]["text"]


async def test_run_command_timeout(ctx):
    with _patch_subprocess(side_effect=subprocess.TimeoutExpired("sleep", 1)):
        result = await run_command(CommandInput(commands=["sleep 100"]), ctx)
    assert result.is_error
    text = result.content[0]["text"]
    assert "timed out" in text and "60 seconds" in text


async def test_run_command_file_not_found(ctx):
    with _patch_subprocess(side_effect=FileNotFoundError()):
        result = await run_command(CommandInput(commands=["ls"], working_directory="/nonexistent/path"), ctx)
    assert result.is_error
    assert "/nonexistent/path" in result.content[0]["text"]


async def test_run_command_generic_exception(ctx):
    with _patch_subprocess(side_effect=RuntimeError("unexpected failure")):
        result = await run_command(CommandInput(commands=["something"]), ctx)
    assert result.is_error
    assert "unexpected failure" in result.content[0]["text"]


# ── Working directory ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("working_directory, expected_cwd", [
    (None, "/tmp/hg-test-wt/s-1"),  # falls back to session.working_directory()
    ("/custom/dir", "/custom/dir"),  # explicit override
])
async def test_run_command_working_directory(ctx, working_directory, expected_cwd):
    captured: dict = {}

    async def mock_run_subprocess(*args, **kwargs):
        captured.update(kwargs)
        return _completed(returncode=0)

    inp = CommandInput(commands=["pwd"], working_directory=working_directory)
    with patch("hypergolic.contrib.tools.command.run_subprocess", new=mock_run_subprocess):
        await run_command(inp, ctx)
    assert captured["cwd"] == expected_cwd


# ── Timeout / env defaults ────────────────────────────────────────────────────


async def test_run_command_honors_timeout(ctx):
    captured: dict = {}

    async def mock_run_subprocess(*args, **kwargs):
        captured.update(kwargs)
        return _completed(returncode=0)

    with patch("hypergolic.contrib.tools.command.run_subprocess", new=mock_run_subprocess):
        await run_command(CommandInput(commands=["sleep 1"], timeout=300), ctx)

    assert captured["timeout"] == 300


async def test_run_command_uses_default_timeout_and_inherits_env(ctx):
    captured: dict = {}

    async def mock_run_subprocess(*args, **kwargs):
        captured.update(kwargs)
        return _completed(returncode=0)

    with patch("hypergolic.contrib.tools.command.run_subprocess", new=mock_run_subprocess):
        await run_command(CommandInput(commands=["env"]), ctx)

    assert captured["timeout"] == 60
    assert "env" not in captured  # subprocess inherits the parent environment
