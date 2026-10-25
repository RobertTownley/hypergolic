"""Tests for tools/file_walker.py."""

from pathlib import Path
from unittest.mock import patch

from hypergolic.tools.file_walker import SKIP_DIRS, walk_files


def test_walk_basic(tmp_path):
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    files = list(walk_files(tmp_path))
    names = {f.name for f in files}
    assert names == {"a.py", "b.txt"}


def test_walk_recursive(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "c.py").write_text("c")
    files = list(walk_files(tmp_path))
    assert any(f.name == "c.py" for f in files)


def test_walk_skips_hidden_by_default(tmp_path):
    (tmp_path / ".secret").write_text("s")
    (tmp_path / "visible.py").write_text("v")
    files = list(walk_files(tmp_path))
    assert all(not f.name.startswith(".") for f in files)


def test_walk_includes_hidden_when_requested(tmp_path):
    (tmp_path / ".secret").write_text("s")
    files = list(walk_files(tmp_path, include_hidden=True))
    assert any(f.name == ".secret" for f in files)


def test_walk_skips_skip_dirs(tmp_path):
    for d in ["node_modules", "__pycache__", ".git"]:
        sd = tmp_path / d
        sd.mkdir()
        (sd / "inner.py").write_text("x")
    files = list(walk_files(tmp_path, include_hidden=True))
    for f in files:
        assert not any(p in SKIP_DIRS for p in f.parts)


def test_walk_file_glob(tmp_path):
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    files = list(walk_files(tmp_path, file_glob="*.py"))
    assert len(files) == 1
    assert files[0].name == "a.py"


def test_walk_max_depth(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "deep.py").write_text("x")
    (tmp_path / "a" / "shallow.py").write_text("y")
    files = list(walk_files(tmp_path, max_depth=2))
    names = {f.name for f in files}
    assert "shallow.py" in names
    assert "deep.py" not in names


def test_walk_permission_error(tmp_path):
    """PermissionError on iterdir is handled gracefully."""
    (tmp_path / "ok.py").write_text("x")
    bad = tmp_path / "bad_dir"
    bad.mkdir()
    with patch.object(Path, "iterdir", side_effect=PermissionError):
        files = list(walk_files(tmp_path))
    assert files == []


def test_walk_respects_gitignore(tmp_path):
    """Files matching .gitignore patterns are skipped."""
    (tmp_path / ".gitignore").write_text("*.log\n")
    (tmp_path / "app.py").write_text("x")
    (tmp_path / "debug.log").write_text("x")
    files = list(walk_files(tmp_path, include_hidden=True))
    names = {f.name for f in files}
    assert "app.py" in names
    assert "debug.log" not in names


def test_walk_ignored_dir(tmp_path):
    (tmp_path / ".gitignore").write_text("build/\n")
    build = tmp_path / "build"
    build.mkdir()
    (build / "out.js").write_text("x")
    files = list(walk_files(tmp_path, include_hidden=True))
    names = {f.name for f in files}
    assert "out.js" not in names
