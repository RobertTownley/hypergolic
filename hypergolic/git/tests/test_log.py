"""Tests for git/log.py."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from hypergolic.git.log import get_git_commit_detail, get_git_log


def _ok(stdout=""):
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


# ── get_git_log ─────────────────────────────────────────────────────


def test_get_git_log_basic(tmp_path):
    sep = "\x1f"
    line = sep.join(["abcdef", "abc", "Dev", "2025-01-01", "init", "HEAD -> main"])
    with patch("hypergolic.git.log.run_git_command", return_value=_ok(line + "\n")):
        result = get_git_log(count=10, repo=tmp_path)
    assert len(result.entries) == 1
    assert result.entries[0].hash == "abcdef"
    assert result.entries[0].message == "init"


def test_get_git_log_skips_malformed(tmp_path):
    with patch("hypergolic.git.log.run_git_command", return_value=_ok("bad line\n")):
        result = get_git_log(repo=tmp_path)
    assert result.entries == []


def test_get_git_log_default_repo():
    with (
        patch("hypergolic.git.log.git_repo_root", return_value=Path("/r")),
        patch("hypergolic.git.log.run_git_command", return_value=_ok()),
    ):
        get_git_log()


# ── get_git_commit_detail ───────────────────────────────────────────


def test_commit_detail_basic(tmp_path):
    sep = "\x1f"
    log_out = sep.join(["full_hash", "short", "Author", "2025-01-01", "msg"])
    call_count = 0

    def mock_run(*args, cwd=None, check=False):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _ok(log_out + "\n")
        return _ok("diff output")

    with patch("hypergolic.git.log.run_git_command", side_effect=mock_run):
        result = get_git_commit_detail("full_hash", repo=tmp_path)
    assert result.hash == "full_hash"
    assert result.author == "Author"
    assert result.diff == "diff output"


def test_commit_detail_malformed(tmp_path):
    with patch("hypergolic.git.log.run_git_command", return_value=_ok("bad\n")):
        result = get_git_commit_detail("abc123", repo=tmp_path)
    assert result.hash == "abc123"
    assert result.short_hash == "abc123"
    assert result.author == ""


def test_commit_detail_default_repo():
    sep = "\x1f"
    log_out = sep.join(["h", "s", "a", "d", "m"])
    with (
        patch("hypergolic.git.log.git_repo_root", return_value=Path("/r")),
        patch("hypergolic.git.log.run_git_command", return_value=_ok(log_out)),
    ):
        get_git_commit_detail("h")
