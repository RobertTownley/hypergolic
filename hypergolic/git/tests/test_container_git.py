from pathlib import Path
from unittest.mock import patch

import pytest

import hypergolic.config.settings as config
from hypergolic.git.commands import run_git_command
from hypergolic.git.container_git import (
    SandboxRepoUnavailable,
    _argv,
    _classify,
    routes_to_sandbox,
)
from hypergolic.sandbox.model.constants import HARNESS_MOUNT, SHARED_MOUNT, WORKSPACE_MOUNT
from tests.conftest import make_project


def test_routes_to_sandbox_none_and_host_repo(tmp_path: Path):
    assert not routes_to_sandbox(None)
    (tmp_path / ".git").mkdir()
    assert not routes_to_sandbox(tmp_path)


def test_routes_to_sandbox_container_gitdir_pointer(tmp_path: Path):
    (tmp_path / ".git").write_text("gitdir: /var/git/gone.git\n")
    assert routes_to_sandbox(tmp_path)


def test_harness_clone_routes_with_harness_mount(tmp_path: Path, monkeypatch, sample_app):
    monkeypatch.setattr(config, "INTERNALS_DIR", tmp_path)
    from tests.conftest import make_session

    sid = make_session(project_id="p-1")
    harness = tmp_path / "sessions" / sid / "harness"
    harness.mkdir(parents=True)
    (harness / ".git").write_text("gitdir: /var/git/gone.git\n")

    assert routes_to_sandbox(harness)
    assert _classify(harness) == (HARNESS_MOUNT, sid, "p-1")


def test_shared_clone_routes_to_its_session(tmp_path: Path, monkeypatch):
    from tests.conftest import make_session

    monkeypatch.setattr(config, "INTERNALS_DIR", tmp_path)
    make_project("p-sh", "P", "/tmp/p-sh")
    sid = make_session(project_id="p-sh")
    path = tmp_path / "sessions" / sid / "shared"
    path.mkdir(parents=True)
    (path / ".git").write_text("gitdir: /var/git/gone.git\n")

    assert routes_to_sandbox(path)
    assert _classify(path) == (SHARED_MOUNT, sid, "p-sh")


def test_argv_raises_when_sandbox_down(tmp_path: Path):
    with patch(
        "hypergolic.git.container_git._classify",
        return_value=(WORKSPACE_MOUNT, "s-1", "p-1"),
    ), patch(
        "hypergolic.git.container_git._container_for", return_value=None,
    ):
        with pytest.raises(SandboxRepoUnavailable) as exc:
            _argv(tmp_path, ("status",))
    assert "not running" in str(exc.value)


def test_argv_execs_container_git(tmp_path: Path):
    with patch(
        "hypergolic.git.container_git._classify",
        return_value=(WORKSPACE_MOUNT, "s-1", "p-1"),
    ), patch(
        "hypergolic.git.container_git._container_for", return_value="hg-x-dev-1",
    ):
        argv = _argv(tmp_path, ("status", "--porcelain"))
    assert argv[:4] == ["docker", "exec", "-i", "hg-x-dev-1"]
    assert argv[4:] == ["git", "-C", WORKSPACE_MOUNT, "status", "--porcelain"]


def test_run_git_command_delegates_for_sandbox_workspace(tmp_path: Path):
    (tmp_path / ".git").write_text("gitdir: /var/git/gone.git\n")
    with patch(
        "hypergolic.git.container_git._container_for", return_value=None,
    ):
        with pytest.raises(SandboxRepoUnavailable):
            run_git_command("status", cwd=tmp_path)
