"""Tests for hypergolic.tools.subprocess_util."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


from hypergolic.tools.subprocess_util import (
    _build_env,
    _strip_own_virtual_env,
    has_ripgrep,
    load_env_file,
    run_subprocess,
)
import sys


def test_load_env_file_parsing(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# This is a comment\n"
        "\n"
        "KEY=value\n"
        'DB_URL="postgres://localhost/db"\n'
        "SECRET='my secret value'\n"
        "NO_EQUALS_HERE\n"
        "\n"
    )
    expected = {
        "KEY": "value",
        "DB_URL": "postgres://localhost/db",
        "SECRET": "my secret value",
    }
    assert load_env_file(env_file) == expected
    assert load_env_file(str(env_file)) == expected  # str paths accepted


def test_load_env_file_nonexistent_file(tmp_path: Path):
    assert load_env_file(tmp_path / "does_not_exist.env") == {}


def test_build_env_all_none_returns_none():
    result = _build_env(
        env_file=None,
        env_overrides=None,
        cwd=None,
        existing_env=None,
    )
    assert result is None


def test_build_env_merges_file_overrides_and_existing(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("FROM_FILE=yes\nKEY=from_file\n")
    result = _build_env(
        env_file=env_file,
        env_overrides={"KEY": "from_override"},
        cwd=None,
        existing_env={"BASE": "base"},
    )
    assert result is not None
    assert result["FROM_FILE"] == "yes"
    assert result["BASE"] == "base"
    assert result["KEY"] == "from_override"  # overrides beat the file


def test_build_env_relative_env_file_resolved_against_cwd(tmp_path: Path):
    env_file = tmp_path / "project.env"
    env_file.write_text("PROJ=hello\n")
    result = _build_env(
        env_file="project.env",
        env_overrides=None,
        cwd=str(tmp_path),
        existing_env={},
    )
    assert result is not None
    assert result["PROJ"] == "hello"


def test_build_env_uses_os_environ_when_no_existing_env():
    """When existing_env is None but env_overrides is provided, os.environ is used as base."""
    result = _build_env(
        env_file=None,
        env_overrides={"TEST_OVERRIDE": "test_val"},
        cwd=None,
        existing_env=None,
    )
    assert result is not None
    assert result["TEST_OVERRIDE"] == "test_val"


def test_has_ripgrep_returns_bool():
    result = has_ripgrep()
    assert isinstance(result, bool)


async def test_run_subprocess_defaults_capture_output_and_text():
    """run_subprocess sets capture_output=True and text=True by default."""
    fake_result = MagicMock(spec=subprocess.CompletedProcess)

    with patch("subprocess.run", return_value=fake_result) as mock_run:
        result = await run_subprocess(["echo", "hello"])

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["capture_output"] is True
    assert call_kwargs["text"] is True
    assert result is fake_result


async def test_run_subprocess_caller_can_override_defaults():
    """Caller-supplied capture_output/text values are respected."""
    fake_result = MagicMock(spec=subprocess.CompletedProcess)

    with patch("subprocess.run", return_value=fake_result) as mock_run:
        await run_subprocess(["echo"], capture_output=False, text=False)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["capture_output"] is False
    assert call_kwargs["text"] is False


async def test_run_subprocess_with_env_overrides():
    """env_overrides are built into kwargs[env] before calling subprocess.run."""
    fake_result = MagicMock(spec=subprocess.CompletedProcess)

    with patch("subprocess.run", return_value=fake_result) as mock_run:
        await run_subprocess(
            ["env"],
            env_overrides={"MY_VAR": "my_value"},
        )

    call_kwargs = mock_run.call_args[1]
    assert "env" in call_kwargs
    assert call_kwargs["env"]["MY_VAR"] == "my_value"


async def test_run_subprocess_no_env_kwargs_when_all_none(monkeypatch):
    """When no env_file, env_overrides, or env kwarg are given, env is not injected."""
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    fake_result = MagicMock(spec=subprocess.CompletedProcess)

    with patch("subprocess.run", return_value=fake_result) as mock_run:
        await run_subprocess(["echo"])

    call_kwargs = mock_run.call_args[1]
    assert "env" not in call_kwargs


def test_strip_own_virtual_env_removes_when_matches_sys_prefix():
    env = {"VIRTUAL_ENV": sys.prefix, "OTHER": "keep"}
    result = _strip_own_virtual_env(env)
    assert "VIRTUAL_ENV" not in result
    assert result["OTHER"] == "keep"


def test_strip_own_virtual_env_preserves_foreign_value():
    env = {"VIRTUAL_ENV": "/some/other/venv", "OTHER": "keep"}
    result = _strip_own_virtual_env(env)
    assert result["VIRTUAL_ENV"] == "/some/other/venv"


def test_strip_own_virtual_env_no_op_when_unset():
    env = {"OTHER": "keep"}
    result = _strip_own_virtual_env(env)
    assert result == {"OTHER": "keep"}


async def test_run_subprocess_strips_own_virtual_env_when_inheriting(monkeypatch):
    """Implicit env inheritance drops our own VIRTUAL_ENV so child `uv run` doesn't warn."""
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    fake_result = MagicMock(spec=subprocess.CompletedProcess)

    with patch("subprocess.run", return_value=fake_result) as mock_run:
        await run_subprocess(["echo"])

    call_kwargs = mock_run.call_args[1]
    assert "env" in call_kwargs
    assert "VIRTUAL_ENV" not in call_kwargs["env"]


async def test_run_subprocess_preserves_foreign_virtual_env(monkeypatch):
    """A deliberately different VIRTUAL_ENV set in the environment is passed through."""
    monkeypatch.setenv("VIRTUAL_ENV", "/deliberately/different/venv")
    fake_result = MagicMock(spec=subprocess.CompletedProcess)

    with patch("subprocess.run", return_value=fake_result) as mock_run:
        await run_subprocess(["echo"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["env"]["VIRTUAL_ENV"] == "/deliberately/different/venv"
