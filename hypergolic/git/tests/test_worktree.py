"""Tests for hypergolic.git.worktree — workspace naming helpers."""

from __future__ import annotations

from pathlib import Path

from hypergolic.git.worktree import (
    sanitize_branch_for_path,
    worktree_branch_name,
    worktree_path_for,
    worktrees_root,
)


def test_sanitize_branch_for_path_replaces_slashes() -> None:
    assert sanitize_branch_for_path("main") == "main"
    assert sanitize_branch_for_path("feature/x") == "feature-x"
    assert sanitize_branch_for_path("a/b/c") == "a-b-c"


def test_sanitize_branch_for_path_strips_unsafe_chars() -> None:
    assert ":" not in sanitize_branch_for_path("weird:branch")
    assert " " not in sanitize_branch_for_path("with space")


def test_worktree_branch_name_uses_base_and_session_id() -> None:
    sid = "ABCDEF012345"
    assert worktree_branch_name(sid, "main") == f"main-{sid}"
    assert worktree_branch_name(sid, "feature/x") == f"feature/x-{sid}"


def test_worktree_path_for_layout(worktrees_home: Path) -> None:
    path = worktree_path_for("proj-1", "main-ABC")
    assert path == worktrees_home / "proj-1" / "main-ABC"
    # Slash in branch name → dash in directory.
    path2 = worktree_path_for("proj-1", "feature/x-ABC")
    assert path2 == worktrees_home / "proj-1" / "feature-x-ABC"


def test_worktrees_root_uses_setting(worktrees_home: Path) -> None:
    assert worktrees_root() == worktrees_home
