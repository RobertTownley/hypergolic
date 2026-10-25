"""Tests for hypergolic CLI modules: app, doctor_cmd, setup, update_cmd, version."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
import typer
from typer.testing import CliRunner

from hypergolic.cli import doctor_cmd, update_cmd
from hypergolic.cli.app import app, _version_callback
from hypergolic.cli.setup import (
    _find_ui_source_dir,
    build_ui,
    run_migrations,
)
from hypergolic.cli.version import get_version
# version.py
def test_get_version_returns_string():
    v = get_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_get_version_returns_unknown_on_exception():
    with patch("hypergolic.cli.version.pkg_version", side_effect=Exception("not found")):
        v = get_version()
    assert v == "unknown"
# app.py — CLI entry point
@pytest.mark.parametrize("flag", ["--version", "-v"])
def test_app_version_flag(flag):
    result = CliRunner().invoke(app, [flag])
    assert result.exit_code == 0
    assert "hypergolic" in result.output


def test_version_callback():
    _version_callback(False)  # no Exit raised
    with pytest.raises(typer.Exit):
        _version_callback(True)


def test_app_registers_commands():
    result = CliRunner().invoke(app, ["--help"])
    for cmd in ("init", "update", "doctor"):
        assert cmd in result.output
# doctor_cmd.py
def _doctor_dir(root: Path, *, main: str | None = "# valid python\n",
                pyproject: bool = True) -> None:
    if main is not None:
        (root / "main.py").write_text(main)
    if pyproject:
        (root / "pyproject.toml").write_text("[project]\n")


def _run_doctor(root: Path, *, docker: bool = True):
    doctor_app = typer.Typer()
    doctor_app.command()(doctor_cmd.doctor)
    with (
        patch.object(doctor_cmd, "HARNESS_DIR", root),
        patch("hypergolic.cli.doctor_cmd.reconcile_worktrees") as mock_rec,
        patch("hypergolic.db.container.docker_running", return_value=docker),
        patch("hypergolic.db.container.ensure_postgres"),
    ):
        mock_rec.return_value.is_clean.return_value = True
        return CliRunner().invoke(doctor_app, [])


def test_doctor_all_checks_pass(tmp_path):
    _doctor_dir(tmp_path)
    result = _run_doctor(tmp_path)
    assert result.exit_code == 0


@pytest.mark.parametrize("kwargs,needle", [
    (dict(main=None), "main.py"),
    (dict(main="def broken(:\n"), "main.py"),
    (dict(pyproject=False), "pyproject.toml"),
], ids=["missing_main", "syntax_error_main", "missing_pyproject"])
def test_doctor_reports_issues(tmp_path, kwargs, needle):
    _doctor_dir(tmp_path, **kwargs)
    result = _run_doctor(tmp_path)
    assert result.exit_code == 1
    assert needle in result.output


def test_doctor_docker_down_is_issue(tmp_path):
    _doctor_dir(tmp_path)
    result = _run_doctor(tmp_path, docker=False)
    assert result.exit_code == 1
    assert "Docker" in result.output
# setup.py
def test_setup_run_migrations():
    """run_migrations calls alembic upgrade head."""
    with patch("hypergolic.cli.setup.alembic_command.upgrade") as mock_upgrade:
        run_migrations()

    mock_upgrade.assert_called_once()
    assert mock_upgrade.call_args[0][1] == "head"
    # fileConfig in env.py would replace the harness's root handlers.
    assert mock_upgrade.call_args[0][0].attributes["configure_logger"] is False


def test_setup_build_ui_no_source():
    """build_ui raises Exit(1) when no UI source found."""
    with (
        patch("hypergolic.cli.setup._find_ui_source_dir", return_value=None),
        pytest.raises((SystemExit, typer.Exit, click.exceptions.Exit)),
    ):
        build_ui()


@pytest.mark.parametrize("run_returncodes", [[1], [0, 1]],
                         ids=["install_fails", "build_fails"])
def test_setup_build_ui_pnpm_failure(tmp_path, run_returncodes):
    """build_ui raises Exit(1) when pnpm install or pnpm build fails."""
    fake_ui = tmp_path / "ui"
    fake_ui.mkdir()
    (fake_ui / "package.json").write_text("{}")

    with (
        patch("hypergolic.cli.setup._find_ui_source_dir", return_value=fake_ui),
        patch("hypergolic.cli.setup.subprocess.run",
              side_effect=[MagicMock(returncode=rc) for rc in run_returncodes]),
        pytest.raises((SystemExit, typer.Exit, click.exceptions.Exit)),
    ):
        build_ui()


def test_setup_build_ui_success(tmp_path):
    """build_ui succeeds when both pnpm commands succeed."""
    fake_ui = tmp_path / "ui"
    fake_ui.mkdir()
    (fake_ui / "package.json").write_text("{}")

    with (
        patch("hypergolic.cli.setup._find_ui_source_dir", return_value=fake_ui),
        patch("hypergolic.cli.setup.subprocess.run", return_value=MagicMock(returncode=0)),
    ):
        build_ui()  # Should not raise


def test_find_ui_source_dir_cwd_candidate(tmp_path):
    """_find_ui_source_dir returns the ui/ subdir in cwd if it has package.json."""
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "package.json").write_text("{}")

    with patch("hypergolic.cli.setup.Path.cwd", return_value=tmp_path):
        assert _find_ui_source_dir() == ui_dir


def test_find_ui_source_dir_none_when_missing(tmp_path):
    """_find_ui_source_dir returns None when no ui/ found."""
    with (
        patch("hypergolic.cli.setup.Path.cwd", return_value=tmp_path),
        patch("hypergolic.cli.setup._package_root", return_value=tmp_path),
    ):
        assert _find_ui_source_dir() is None
# update_cmd.py
def _run_update():
    update_app = typer.Typer()
    update_app.command()(update_cmd.update)
    return CliRunner().invoke(update_app, [])


def test_update_no_hypergolic_dir(tmp_path):
    """update exits with 1 if HARNESS_DIR doesn't exist."""
    with patch.object(update_cmd, "HARNESS_DIR", tmp_path / "nonexistent_dir"):
        result = _run_update()

    assert result.exit_code == 1
    assert "Run `hypergolic init`" in result.output or "does not exist" in result.output


def test_update_regenerates_config_and_syncs(tmp_path):
    """update regenerates pyproject + gitignore (defaults ship with the
    package) and runs uv sync so users don't have to do it manually."""
    with (
        patch("hypergolic.cli.update_cmd.HARNESS_DIR", tmp_path),
        patch("hypergolic.cli.update_cmd.generate_pyproject") as mock_gen,
        patch("hypergolic.cli.update_cmd.setup_gitignore") as mock_gi,
        patch("hypergolic.cli.update_cmd._run_uv_sync") as mock_sync,
    ):
        result = _run_update()

    assert result.exit_code == 0
    assert mock_gen.called
    assert mock_gi.called
    mock_sync.assert_called_once()
