"""Tests for git/actions.py."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from hypergolic.git.actions import (
    git_discard,
    git_stage,
    git_unstage,
)
from hypergolic.git.commands import GitCommandError
from tests.helpers.git import init_repo, run_git


def _ok(stdout=""):
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


# ── git_stage / git_unstage ─────────────────────────────────────────


def test_git_stage_success(tmp_path):
    with patch("hypergolic.git.actions.run_git_command", return_value=_ok()) as mock:
        git_stage(["a.py"], repo=tmp_path)
    mock.assert_called_once_with("add", "--", "a.py", cwd=tmp_path, check=True)


def test_git_stage_error(tmp_path):
    with patch("hypergolic.git.actions.run_git_command", side_effect=GitCommandError("add", 1, "err")):
        with pytest.raises(GitCommandError):
            git_stage(["bad.py"], repo=tmp_path)


def test_git_unstage_success(tmp_path):
    with patch("hypergolic.git.actions.run_git_command", return_value=_ok()) as mock:
        git_unstage(["a.py"], repo=tmp_path)
    mock.assert_called_once_with("reset", "HEAD", "--", "a.py", cwd=tmp_path, check=True)


# ── git_discard ────────────────────────────────────────────────────


def test_git_discard_tracked(tmp_path):
    # status returns empty -> nothing untracked -> checkout the tracked file
    with patch("hypergolic.git.actions.run_git_command", return_value=_ok()) as mock:
        git_discard(["a.py"], repo=tmp_path)
    mock.assert_any_call("checkout", "--", "a.py", cwd=tmp_path, check=True)


@pytest.mark.parametrize("name", ["new.py", "un tracked.py"])
def test_git_discard_untracked_file(tmp_path, name):
    """Untracked files (including paths with spaces) are discarded via clean."""
    init_repo(tmp_path)
    (tmp_path / name).write_text("x = 1\n")
    git_discard([name], repo=tmp_path)
    assert not (tmp_path / name).exists()


def test_git_discard_staged_new_file(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "staged.py").write_text("x = 1\n")
    run_git(tmp_path, "add", "staged.py")
    git_discard(["staged.py"], repo=tmp_path)
    assert not (tmp_path / "staged.py").exists()


@pytest.mark.parametrize("name", ["a.py", "a b.py"])
def test_git_discard_tracked_modification(tmp_path, name):
    init_repo(tmp_path)
    (tmp_path / name).write_text("orig\n")
    run_git(tmp_path, "add", name)
    run_git(tmp_path, "commit", "-qm", "init")
    (tmp_path / name).write_text("changed\n")
    git_discard([name], repo=tmp_path)
    assert (tmp_path / name).read_text() == "orig\n"


def test_git_discard_mixed(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "a.py").write_text("orig\n")
    run_git(tmp_path, "add", "a.py")
    run_git(tmp_path, "commit", "-qm", "init")
    (tmp_path / "a.py").write_text("changed\n")
    (tmp_path / "new.py").write_text("y = 2\n")
    (tmp_path / "staged.py").write_text("z = 3\n")
    run_git(tmp_path, "add", "staged.py")
    git_discard(["a.py", "new.py", "staged.py"], repo=tmp_path)
    assert (tmp_path / "a.py").read_text() == "orig\n"
    assert not (tmp_path / "new.py").exists()
    assert not (tmp_path / "staged.py").exists()


# ── default repo fallbacks ──────────────────────────────────────────


@pytest.mark.parametrize("action", [
    lambda: git_stage(["x"]),
    lambda: git_unstage(["x"]),
    lambda: git_discard(["x"]),
], ids=["stage", "unstage", "discard"])
def test_default_repo_fallback(action):
    with (
        patch("hypergolic.git.actions.git_repo_root", return_value=Path("/r")),
        patch("hypergolic.git.actions.run_git_command", return_value=_ok("main\n")),
    ):
        action()
