import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from hypergolic.git.commands import (
    GitCommandError,
    git_repo_root,
    run_git_command,
    unmerged_commit_count,
)
from tests.helpers.git import clone_workspace, commit_file, init_repo, run_git


def test_git_command_error_attrs():
    err = GitCommandError(command="push", returncode=128, stderr="fatal", stdout="out")
    assert err.command == "push"
    assert err.returncode == 128
    assert err.stderr == "fatal"
    assert err.stdout == "out"
    assert "push" in str(err)
    assert "128" in str(err)


def test_git_command_error_default_stdout():
    err = GitCommandError("pull", 1, "err")
    assert err.stdout == ""


def test_git_repo_root_success():
    with patch("hypergolic.git.commands.subprocess.run") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="/repo\n")
        assert git_repo_root() == Path("/repo")


def test_git_repo_root_fallback_on_error():
    with patch("hypergolic.git.commands.subprocess.run", side_effect=FileNotFoundError):
        assert git_repo_root() == Path.cwd()


def test_git_repo_root_fallback_on_bad_exit():
    with patch(
        "hypergolic.git.commands.subprocess.run",
        side_effect=subprocess.CalledProcessError(128, "git"),
    ):
        assert git_repo_root() == Path.cwd()


def test_run_git_command_success(tmp_path):
    with patch("hypergolic.git.commands.subprocess.run") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
        result = run_git_command("status", cwd=tmp_path)
    assert result.stdout == "ok"


def test_run_git_command_check_raises(tmp_path):
    with patch("hypergolic.git.commands.subprocess.run") as mock:
        mock.return_value = subprocess.CompletedProcess(
            [], 1, stdout="out", stderr="err",
        )
        with pytest.raises(GitCommandError) as exc:
            run_git_command("add", cwd=tmp_path, check=True)
    assert exc.value.command == "add"


def test_run_git_command_check_false_no_raise(tmp_path):
    with patch("hypergolic.git.commands.subprocess.run") as mock:
        mock.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        result = run_git_command("diff", cwd=tmp_path, check=False)
    assert result.returncode == 1


def test_run_git_command_no_args(tmp_path):
    with patch("hypergolic.git.commands.subprocess.run") as mock:
        mock.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="e")
        with pytest.raises(GitCommandError) as exc:
            run_git_command(cwd=tmp_path, check=True)
    assert exc.value.command == "unknown"


def test_run_git_command_default_cwd():
    with (
        patch("hypergolic.git.commands.git_repo_root", return_value=Path("/r")),
        patch("hypergolic.git.commands.subprocess.run") as mock,
    ):
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        run_git_command("log")
    assert mock.call_args[1]["cwd"] == Path("/r")


@pytest.fixture
def session_clone(tmp_path):
    repo = tmp_path / "proj"
    init_repo(repo)
    ws = tmp_path / "ws"
    clone_workspace(repo, ws, "main-s")
    return repo, ws


@pytest.mark.timeout(10)
def test_unmerged_commit_count_counts_branch_work(session_clone):
    _, ws = session_clone
    assert unmerged_commit_count(ws, "main", "main-s") == 0
    commit_file(ws, "a.txt", "a\n", "w")
    assert unmerged_commit_count(ws, "main", "main-s") == 1


@pytest.mark.timeout(10)
def test_unmerged_commit_count_ignores_squash_landed_work_and_reverse_merges(session_clone):
    repo, ws = session_clone
    commit_file(ws, "a.txt", "a\n", "feat: a")
    commit_file(repo, "other.txt", "other\n", "chore: other")
    run_git(ws, "fetch", "origin")
    run_git(ws, "merge", "--no-edit", "origin/main")
    run_git(repo, "fetch", str(ws), "main-s")
    run_git(repo, "merge", "--squash", "FETCH_HEAD")
    run_git(repo, "commit", "-m", "feat: a (squashed)")
    run_git(ws, "fetch", "origin", "main:main")

    assert unmerged_commit_count(ws, "main", "main-s") == 0
