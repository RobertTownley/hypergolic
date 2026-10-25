"""Tests for hypergolic.git.changes (inline changes payload)."""
from __future__ import annotations

from pathlib import Path

import pytest

from hypergolic.git.changes import get_git_changes
from tests.helpers.git import commit_file, init_repo, run_git

pytestmark = pytest.mark.timeout(15)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    init_repo(r)
    (r / "keep.txt").write_text("keep\n")
    run_git(r, "add", "-A")
    run_git(r, "commit", "-m", "seed")
    run_git(r, "checkout", "-b", "feat")
    return r


def test_clean_tree(repo: Path):
    resp = get_git_changes(repo, "uncommitted", "main", session_id="s1")
    assert resp.session_id == "s1"
    assert resp.files == []


def test_uncommitted_ignores_committed_work(repo: Path):
    commit_file(repo, "done.txt", "done\n", "committed")
    (repo / "keep.txt").write_text("keep\nedited\n")
    resp = get_git_changes(repo, "uncommitted", "main")
    assert [f.path for f in resp.files] == ["keep.txt"]
    assert "+edited" in resp.files[0].patch


def test_all_mode_includes_commits_and_edits(repo: Path):
    commit_file(repo, "done.txt", "done\n", "committed")
    (repo / "keep.txt").write_text("keep\nedited\n")
    resp = get_git_changes(repo, "all", "main")
    assert [f.path for f in resp.files] == ["done.txt", "keep.txt"]


def test_untracked_gets_synthetic_patch(repo: Path):
    (repo / "new.txt").write_text("a\nb\n")
    resp = get_git_changes(repo, "uncommitted", "main")
    assert [f.path for f in resp.files] == ["new.txt"]
    f = resp.files[0]
    assert f.status == "?"
    assert f.additions == 2
    assert "+a" in f.patch


def test_all_mode_without_base_falls_back_to_head(repo: Path):
    (repo / "keep.txt").write_text("edit\n")
    resp = get_git_changes(repo, "all", None)
    assert [f.path for f in resp.files] == ["keep.txt"]
