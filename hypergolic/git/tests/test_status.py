"""Tests for git/status.py."""

import subprocess
from pathlib import Path
from unittest.mock import patch


from hypergolic.git.status import _parse_numstat, get_git_status


def _mock_run(stdout_map: dict[str, str]):
    """Return a side_effect that dispatches by the first git arg."""
    def side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        for key, stdout in stdout_map.items():
            if key in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
    return side_effect


# ── _parse_numstat ─────────────────────────────────────────────────


def test_parse_numstat_basic(tmp_path):
    stdout = "3\t1\tsrc/a.py\n0\t5\tsrc/b.py\n"
    with patch("hypergolic.git.status.run_git_command") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")
        stats = _parse_numstat(tmp_path, staged=True)
    assert stats["src/a.py"] == (3, 1)
    assert stats["src/b.py"] == (0, 5)


def test_parse_numstat_binary(tmp_path):
    """Binary files show '-' for adds/dels."""
    stdout = "-\t-\timage.png\n"
    with patch("hypergolic.git.status.run_git_command") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")
        stats = _parse_numstat(tmp_path, staged=False)
    assert stats["image.png"] == (0, 0)


def test_parse_numstat_malformed(tmp_path):
    stdout = "bad line\n"
    with patch("hypergolic.git.status.run_git_command") as mock:
        mock.return_value = subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")
        assert _parse_numstat(tmp_path, staged=False) == {}


# ── get_git_status ─────────────────────────────────────────────────


def test_get_git_status_basic(tmp_path):
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if cmd == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if "rev-list" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="2\t3\n", stderr="")
        if "--porcelain" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=" M src/a.py\nA  src/b.py\n?? new.txt\n",
                stderr="",
            )
        if "--numstat" in cmd:
            if "--cached" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="5\t0\tsrc/b.py\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="1\t2\tsrc/a.py\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("hypergolic.git.status.run_git_command", side_effect=mock_run):
        status = get_git_status(repo=tmp_path)

    assert status.branch == "main"
    assert status.ahead == 3
    assert status.behind == 2
    assert len(status.unstaged) == 1
    assert status.unstaged[0].path == "src/a.py"
    assert status.unstaged[0].additions == 1
    assert len(status.staged) == 1
    assert status.staged[0].path == "src/b.py"
    assert status.untracked == ["new.txt"]


def test_get_git_status_no_upstream(tmp_path):
    """When rev-list fails, ahead/behind default to 0."""
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if cmd == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="\n", stderr="")
        if "rev-list" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("hypergolic.git.status.run_git_command", side_effect=mock_run):
        status = get_git_status(repo=tmp_path)

    assert status.branch == "HEAD"
    assert status.ahead == 0
    assert status.behind == 0


def test_get_git_status_short_line(tmp_path):
    """Lines shorter than 4 chars are skipped."""
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if "--porcelain" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="XY\n M a.py\n", stderr="")
        if cmd == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("hypergolic.git.status.run_git_command", side_effect=mock_run):
        status = get_git_status(repo=tmp_path)

    assert len(status.unstaged) == 1


def test_get_git_status_rename(tmp_path):
    """Renames use the target path."""
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if "--porcelain" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="R  old.py -> new.py\n", stderr="")
        if cmd == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("hypergolic.git.status.run_git_command", side_effect=mock_run):
        status = get_git_status(repo=tmp_path)

    assert status.staged[0].path == "new.py"


def test_get_git_status_all_changes_against_base(tmp_path):
    """base_branch populates all_changes from the merge-base diff + untracked."""
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if cmd == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="feat\n", stderr="")
        if "rev-list" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        if "--porcelain" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/a.py\n", stderr="")
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="M\tsrc/a.py\nA\tsrc/committed.py\n", stderr="",
            )
        if "--numstat" in cmd and "basesha" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="1\t2\tsrc/a.py\n10\t0\tsrc/committed.py\n", stderr="",
            )
        if "--numstat" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0] == "ls-files":
            return subprocess.CompletedProcess(cmd, 0, stdout="src/new.txt\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("hypergolic.git.status.merge_base", return_value="basesha"),
        patch("hypergolic.git.status.run_git_command", side_effect=mock_run),
    ):
        status = get_git_status(repo=tmp_path, base_branch="main")

    paths = [c.path for c in status.all_changes]
    assert paths == ["src/a.py", "src/committed.py", "src/new.txt"]
    committed = next(c for c in status.all_changes if c.path == "src/committed.py")
    assert committed.status == "A"
    assert committed.additions == 10
    untracked = next(c for c in status.all_changes if c.path == "src/new.txt")
    assert untracked.status == "?"


def test_get_git_status_no_base_branch_skips_all_changes(tmp_path):
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if cmd == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="feat\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("hypergolic.git.status.run_git_command", side_effect=mock_run):
        status = get_git_status(repo=tmp_path)
    assert status.all_changes == []


def test_get_git_status_all_changes_no_merge_base(tmp_path):
    """When merge-base fails, all_changes is empty rather than erroring."""
    def mock_run(*args, cwd=None, check=False):
        cmd = list(args)
        if cmd == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="feat\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("hypergolic.git.status.merge_base", return_value=None),
        patch("hypergolic.git.status.run_git_command", side_effect=mock_run),
    ):
        status = get_git_status(repo=tmp_path, base_branch="main")
    assert status.all_changes == []


def test_get_git_status_default_repo():
    with (
        patch("hypergolic.git.status.git_repo_root", return_value=Path("/r")),
        patch("hypergolic.git.status.run_git_command") as mock,
    ):
        mock.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        get_git_status()
