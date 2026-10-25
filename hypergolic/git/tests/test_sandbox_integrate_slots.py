"""RepoSlot constructors: the app/harness parameterization of integration."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from tests._factories import build_session

import pytest

import hypergolic.config.settings as settings_module
from hypergolic.git.sandbox_integrate import (
    SandboxGitError,
    app_slot,
    harness_slot,
)


def _session(**kw) -> Any:
    defaults: dict[str, Any] = dict(
        sid="s1", project_id="p1", base_branch="main",
        worktree_branch="main-S1", worktree_path="/x/wt",
    )
    return build_session(**{**defaults, **kw})


def test_app_slot():
    project = SimpleNamespace(id="p1", path="/repos/acme")
    slot = app_slot(_session(), cast(Any, project))
    assert slot.repo == "app"
    assert slot.workdir == "/app"
    assert slot.host_repo == Path("/repos/acme")
    assert slot.base_branch == "main"
    assert slot.session_branch == "main-S1"
    assert slot.ref_scope == "p1"


def test_harness_slot(tmp_path, monkeypatch):
    import subprocess

    repo = tmp_path / "hg"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "f").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "i"],
        cwd=repo, check=True, capture_output=True,
    )
    monkeypatch.setattr(settings_module, "HARNESS_DIR", repo)

    slot = harness_slot(_session())
    assert slot.repo == "harness"
    assert slot.workdir == "/harness"
    assert slot.host_repo == repo
    assert slot.base_branch == "main"
    assert slot.session_branch == "main-S1-harness"
    assert slot.ref_scope == "harness"


def test_harness_slot_unusable_repo(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setattr(settings_module, "HARNESS_DIR", plain)
    with pytest.raises(SandboxGitError):
        harness_slot(_session())

async def test_exec_repo_git_translates_sandbox_errors():
    from unittest.mock import AsyncMock, patch

    from hypergolic.git.sandbox_integrate import exec_repo_git
    from hypergolic.sandbox.manager.types import SandboxNotReadyError

    project = SimpleNamespace(id="p1", path="/repos/acme")
    with (
        patch("hypergolic.git.sandbox_integrate.workspace_service", return_value="app"),
        patch(
            "hypergolic.git.sandbox_integrate.exec_in_sandbox",
            AsyncMock(side_effect=SandboxNotReadyError("Sandbox is starting up.")),
        ),
    ):
        with pytest.raises(SandboxGitError, match="starting up"):
            await exec_repo_git(_session(), cast(Any, project), "git status")
