"""Tests for hypergolic.files.tree."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from hypergolic.files.tree import (
    _build_tree,
    _dir_aggregate_status,
    _git_ignored_set,
    _git_status_map,
    _is_ignored,
    build_file_tree,
    get_repo_root,
)

TREE = "hypergolic.files.tree"


def _run(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout)


@pytest.fixture
def mock_run():
    with patch(f"{TREE}.subprocess.run") as m:
        yield m


# ── _is_ignored ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel,ignored,expected",
    [
        ("dist", {"dist"}, True),
        ("dist/bundle.js", {"dist"}, True),
        ("src/app.py", {"dist"}, False),
        ("distribute", {"dist"}, False),
    ],
    ids=["exact", "child", "unrelated", "prefix-not-a-match"],
)
def test_is_ignored(rel, ignored, expected):
    assert _is_ignored(rel, ignored) is expected


# ── _dir_aggregate_status ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "status_map,expected",
    [
        ({}, None),
        ({"src/a.py": "M"}, "M"),
        ({"src/a.py": "MM"}, "M"),
        ({"src/a.py": "AM"}, "M"),
        ({"src/a.py": "A"}, "A"),
        ({"src/a.py": "??"}, "??"),
        ({"src/a.py": "D"}, "D"),
    ],
    ids=["no-children", "modified", "MM", "AM", "added", "untracked", "fallthrough"],
)
def test_dir_aggregate_status(status_map, expected):
    assert _dir_aggregate_status("src", status_map) == expected


# ── _git_status_map ────────────────────────────────────────────────


class TestGitStatusMap:
    def test_parses_porcelain_output(self, mock_run, tmp_path):
        mock_run.return_value = _run(" M src/a.py\n?? new.txt\n")
        assert _git_status_map(tmp_path) == {"src/a.py": "M", "new.txt": "??"}

    def test_uses_destination_side_of_rename(self, mock_run, tmp_path):
        mock_run.return_value = _run("R  old.py -> new.py\n")
        assert "new.py" in _git_status_map(tmp_path)

    def test_skips_lines_shorter_than_4_chars(self, mock_run, tmp_path):
        mock_run.return_value = _run("XX\n M a.py\n")
        assert _git_status_map(tmp_path) == {"a.py": "M"}

    @pytest.mark.parametrize(
        "exc",
        [FileNotFoundError, subprocess.CalledProcessError(1, "git")],
        ids=["missing-binary", "non-zero-exit"],
    )
    def test_returns_empty_on_subprocess_failure(self, mock_run, tmp_path, exc):
        mock_run.side_effect = exc
        assert _git_status_map(tmp_path) == {}


# ── _git_ignored_set ───────────────────────────────────────────────


class TestGitIgnoredSet:
    def test_strips_trailing_slashes(self, mock_run, tmp_path):
        mock_run.return_value = _run("dist/\n.env\n")
        assert _git_ignored_set(tmp_path) == {"dist", ".env"}

    def test_skips_blank_lines(self, mock_run, tmp_path):
        mock_run.return_value = _run("\n  \nnode_modules/\n")
        assert _git_ignored_set(tmp_path) == {"node_modules"}

    def test_returns_empty_on_subprocess_failure(self, mock_run, tmp_path):
        mock_run.side_effect = FileNotFoundError
        assert _git_ignored_set(tmp_path) == set()


# ── _build_tree ──────────────────────────────────────────────────


class TestBuildTree:
    def test_returns_files_and_dirs(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "b.py").touch()
        names = {n.name for n in _build_tree(tmp_path, tmp_path, {}, set())}
        assert names == {"src", "a.py"}

    def test_skips_dotfiles(self, tmp_path):
        (tmp_path / ".hidden").touch()
        (tmp_path / "visible.py").touch()
        names = {n.name for n in _build_tree(tmp_path, tmp_path, {}, set())}
        assert names == {"visible.py"}

    @pytest.mark.parametrize("skipped", ["node_modules", "__pycache__"])
    def test_skips_skip_dirs(self, tmp_path, skipped):
        (tmp_path / skipped).mkdir()
        (tmp_path / skipped / "child").touch()
        nodes = _build_tree(tmp_path, tmp_path, {}, set())
        assert all(n.name != skipped for n in nodes)

    def test_attaches_git_status_for_file(self, tmp_path):
        (tmp_path / "a.py").touch()
        nodes = _build_tree(tmp_path, tmp_path, {"a.py": "M"}, set())
        assert nodes[0].git_status == "M"

    def test_marks_ignored_file(self, tmp_path):
        (tmp_path / "a.py").touch()
        nodes = _build_tree(tmp_path, tmp_path, {}, {"a.py"})
        assert nodes[0].git_status == "ignored"

    def test_marks_ignored_dir(self, tmp_path):
        (tmp_path / "dist").mkdir()
        (tmp_path / "dist" / "bundle.js").touch()
        nodes = _build_tree(tmp_path, tmp_path, {}, {"dist"})
        dist = next(n for n in nodes if n.name == "dist")
        assert dist.git_status == "ignored"

    def test_returns_empty_on_permission_error(self, tmp_path):
        with patch.object(Path, "iterdir", side_effect=PermissionError):
            assert _build_tree(tmp_path, tmp_path, {}, set()) == []

    def test_directories_sorted_before_files(self, tmp_path):
        (tmp_path / "z_file.py").touch()
        (tmp_path / "a_dir").mkdir()
        nodes = _build_tree(tmp_path, tmp_path, {}, set())
        assert nodes[0].is_dir and not nodes[1].is_dir


# ── build_file_tree / get_repo_root ────────────────────────────────────


def test_build_file_tree_uses_provided_root(mock_run, tmp_path):
    (tmp_path / "x.py").touch()
    mock_run.return_value = _run()
    assert len(build_file_tree(repo_root=tmp_path)) == 1


def test_build_file_tree_falls_back_to_git_repo_root(mock_run):
    mock_run.return_value = _run()
    with (
        patch(f"{TREE}.git_repo_root", return_value=Path("/fake")),
        patch(f"{TREE}._build_tree", return_value=[]) as m,
    ):
        build_file_tree()
    m.assert_called_once()


def test_get_repo_root_returns_provided_path():
    assert get_repo_root(Path("/a/b")) == "/a/b"


def test_get_repo_root_falls_back_to_git_repo_root():
    with patch(f"{TREE}.git_repo_root", return_value=Path("/repo")):
        assert get_repo_root() == "/repo"
