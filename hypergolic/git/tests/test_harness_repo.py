"""Harness repo helpers: healing, base-branch resolution, session paths."""

import subprocess
from pathlib import Path

import pytest

import hypergolic.config.settings as settings_module
from hypergolic.git.harness_repo import (
    ensure_harness_repo,
    harness_base_branch,
    harness_session_branch,
    harness_workspace_path,
)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def harness_repo(tmp_path, monkeypatch):
    repo = tmp_path / "dot-hypergolic"
    repo.mkdir()
    _git("init", "-b", "main", cwd=repo)
    _git("config", "user.email", "t@t", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    (repo / "main.py").write_text("# harness\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)
    monkeypatch.setattr(settings_module, "HARNESS_DIR", repo)
    monkeypatch.setattr(settings_module, "INTERNALS_DIR", tmp_path / "internals")
    return repo


def test_no_git_repo_yields_no_base(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setattr(settings_module, "HARNESS_DIR", plain)
    assert harness_base_branch() is None


def test_session_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "INTERNALS_DIR", tmp_path / "internals")
    assert harness_workspace_path("s1") == tmp_path / "internals" / "sessions" / "s1" / "harness"
    assert harness_session_branch("main-S1") == "main-S1-harness"


def test_base_branch_resolves(harness_repo):
    assert harness_base_branch() == "main"


def test_detached_head_yields_no_base(harness_repo):
    _git("checkout", "--detach", cwd=harness_repo)
    assert harness_base_branch() is None


def test_ensure_harness_repo_heals_plain_dir(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "main.py").write_text("# config\n")
    monkeypatch.setattr(settings_module, "HARNESS_DIR", plain)
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "t")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "t@t")

    ensure_harness_repo()
    assert harness_base_branch() == "main"
    # Runtime exhaust is ignored from the very first commit
    assert "worktrees/" in (plain / ".gitignore").read_text()


def test_ensure_harness_repo_leaves_existing_history_alone(harness_repo):
    (harness_repo / "dirty.py").write_text("x = 1\n")
    ensure_harness_repo()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=harness_repo, capture_output=True, text=True
    ).stdout
    assert "dirty.py" in status  # not committed out from under the user


def test_ensure_harness_repo_noop_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "HARNESS_DIR", tmp_path / "nope")

    ensure_harness_repo()
    assert not (tmp_path / "nope").exists()
