"""Tests for tools/gitignore.py."""

from pathlib import Path

from hypergolic.tools.gitignore import (
    GitignoreRules,
    collect_ignore_rules,
    find_git_root,
)


def test_find_git_root_walks_up(tmp_path):
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_git_root(nested) == tmp_path


def test_find_git_root_returns_none_when_no_ancestor(monkeypatch, tmp_path):
    """When no ancestor contains .git, return None."""
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert find_git_root(tmp_path) is None


def test_is_ignored_matches_leaf_directory(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    rules = collect_ignore_rules(tmp_path)
    assert rules.is_ignored(tmp_path / "node_modules") is True


def test_is_ignored_matches_descendants_of_ignored_dir(tmp_path):
    """A non-anchored pattern like ``node_modules/`` ignores all descendants."""
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    rules = collect_ignore_rules(tmp_path)
    assert rules.is_ignored(tmp_path / "node_modules" / "pkg") is True
    assert rules.is_ignored(tmp_path / "node_modules" / "pkg" / "index.js") is True


def test_is_ignored_no_match(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    rules = collect_ignore_rules(tmp_path)
    assert rules.is_ignored(tmp_path / "src" / "App.tsx") is False


def test_is_ignored_anchored_pattern(tmp_path):
    """Patterns containing a slash are anchored to the .gitignore dir."""
    (tmp_path / ".gitignore").write_text("build/out\n")
    rules = collect_ignore_rules(tmp_path)
    assert rules.is_ignored(tmp_path / "build" / "out") is True
    assert rules.is_ignored(tmp_path / "build" / "out" / "file.js") is True
    assert rules.is_ignored(tmp_path / "build" / "other") is False


def test_is_ignored_negation(tmp_path):
    (tmp_path / ".gitignore").write_text("*.log\n!keep.log\n")
    rules = collect_ignore_rules(tmp_path)
    assert rules.is_ignored(tmp_path / "a.log") is True
    assert rules.is_ignored(tmp_path / "keep.log") is False


def test_load_file_noop_when_missing(tmp_path):
    rules = GitignoreRules()
    rules.load_file(tmp_path / "missing")
    assert rules.is_ignored(tmp_path / "any") is False


def test_load_file_skips_comments_and_blank_lines(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("# comment\n\n*.log\n")
    rules = GitignoreRules()
    rules.load_file(gi)
    assert rules.is_ignored(Path("x.log")) is True


def test_collect_ignore_rules_includes_ancestor_files(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("*.log\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / ".gitignore").write_text("*.tmp\n")
    rules = collect_ignore_rules(sub)
    assert rules.is_ignored(sub / "a.log") is True
    assert rules.is_ignored(sub / "a.tmp") is True
