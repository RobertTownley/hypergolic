"""Tests for git/diff.py."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from hypergolic.git.diff import _is_tracked, get_git_diff


# ── _is_tracked ─────────────────────────────────────────────────────


def test_is_tracked_true(tmp_path):
    with patch("hypergolic.git.diff.run_git_command") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        assert _is_tracked("a.py", tmp_path) is True


def test_is_tracked_false(tmp_path):
    with patch("hypergolic.git.diff.run_git_command") as mock:
        mock.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        assert _is_tracked("new.py", tmp_path) is False


# ── get_git_diff ────────────────────────────────────────────────────


def test_get_git_diff_basic(tmp_path):
    with patch("hypergolic.git.diff.run_git_command") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="diff output", stderr="")
        result = get_git_diff("a.py", staged=False, repo=tmp_path)
    assert result.diff == "diff output"
    assert result.path == "a.py"


def test_get_git_diff_staged(tmp_path):
    with patch("hypergolic.git.diff.run_git_command") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="staged diff", stderr="")
        get_git_diff("a.py", staged=True, repo=tmp_path)
    cmd_args = mock.call_args[0]
    assert "--cached" in cmd_args


def test_get_git_diff_no_path(tmp_path):
    with patch("hypergolic.git.diff.run_git_command") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="full diff", stderr="")
        result = get_git_diff(None, staged=False, repo=tmp_path)
    assert result.path == ""
    assert result.diff == "full diff"


def test_get_git_diff_untracked_file(tmp_path):
    """For untracked files, falls back to --no-index diff."""
    call_count = 0

    def mock_run(*args, cwd=None, check=False):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # git diff
            return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
        if call_count == 2:  # git ls-files (not tracked)
            return subprocess.CompletedProcess(list(args), 1, stdout="", stderr="")
        if call_count == 3:  # git diff --no-index
            return subprocess.CompletedProcess(list(args), 0, stdout="new file diff", stderr="")
        return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")

    with patch("hypergolic.git.diff.run_git_command", side_effect=mock_run):
        result = get_git_diff("new.py", staged=False, repo=tmp_path)
    assert result.diff == "new file diff"


def test_get_git_diff_tracked_empty_diff(tmp_path):
    """Tracked file with no changes returns empty diff (no fallback)."""
    call_count = 0

    def mock_run(*args, cwd=None, check=False):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # git diff
            return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
        if call_count == 2:  # git ls-files (tracked)
            return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
        return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")

    with patch("hypergolic.git.diff.run_git_command", side_effect=mock_run):
        result = get_git_diff("a.py", staged=False, repo=tmp_path)
    assert result.diff == ""
    assert call_count == 2  # no fallback needed


def test_get_git_diff_base_branch(tmp_path):
    """base_branch diffs the path against the merge-base."""
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if cmd[0] == "diff" and "basesha" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="base diff", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("hypergolic.git.diff.merge_base", return_value="basesha"),
        patch("hypergolic.git.diff.run_git_command", side_effect=mock_run),
    ):
        result = get_git_diff("a.py", staged=False, repo=tmp_path, base_branch="main")
    assert result.diff == "base diff"
    assert result.path == "a.py"


def test_get_git_diff_base_branch_no_merge_base_falls_back(tmp_path):
    """When merge-base fails, fall through to the regular working-tree diff."""
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if cmd[0] == "diff":
            return subprocess.CompletedProcess(cmd, 0, stdout="worktree diff", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("hypergolic.git.diff.merge_base", return_value=None),
        patch("hypergolic.git.diff.run_git_command", side_effect=mock_run),
    ):
        result = get_git_diff("a.py", staged=False, repo=tmp_path, base_branch="main")
    assert result.diff == "worktree diff"


def test_get_git_diff_base_branch_untracked(tmp_path):
    """Untracked file under base mode falls back to --no-index."""
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if cmd[0] == "diff" and "basesha" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0] == "ls-files":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        if "--no-index" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="new file diff", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("hypergolic.git.diff.merge_base", return_value="basesha"),
        patch("hypergolic.git.diff.run_git_command", side_effect=mock_run),
    ):
        result = get_git_diff("new.py", staged=False, repo=tmp_path, base_branch="main")
    assert result.diff == "new file diff"


def test_get_git_diff_default_repo():
    with (
        patch("hypergolic.git.diff.git_repo_root", return_value=Path("/r")),
        patch("hypergolic.git.diff.run_git_command") as mock,
    ):
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        get_git_diff(None, False)
