"""Tests for hypergolic.git.merge_commit against real merges."""
from __future__ import annotations

from pathlib import Path

import pytest

from hypergolic.git.merge_commit import (
    clean_merge_summary,
    combined_patch,
    commit_message,
    inspect_merge,
    is_merge_commit,
)
from tests.helpers.git import run_git, sync_merge

pytestmark = pytest.mark.timeout(15)


def test_plain_commit_is_not_a_merge(repo: Path):
    sha = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    assert not is_merge_commit(repo, sha)
    assert inspect_merge(repo, sha, target_branch="pr") is None


def test_clean_sync_merge_has_no_conflict_paths(repo: Path):
    pr_tip, merge = sync_merge(repo)
    info = inspect_merge(repo, merge, target_branch="pr", root_branch="main")
    assert info is not None
    assert info.parents[0] == pr_tip
    assert info.merged_from == "main"
    assert info.clean
    assert combined_patch(repo, merge) == ""
    assert clean_merge_summary(info, 2) == (
        "Clean merge of 2 commits from main; no conflict resolutions"
    )
    assert commit_message(repo, merge).startswith("Merge branch 'main' into pr")


def test_conflict_resolution_is_the_merge_diff(repo: Path):
    _, merge = sync_merge(repo, conflict=True)
    info = inspect_merge(repo, merge, target_branch="pr", root_branch="main")
    assert info is not None
    assert info.conflict_paths == ["f.txt"]
    assert not info.clean
    patch = combined_patch(repo, merge)
    assert "diff --cc f.txt" in patch
    assert "++resolved" in patch


def test_merged_from_falls_back_to_sha_without_a_branch(repo: Path):
    _, merge = sync_merge(repo)
    run_git(repo, "branch", "-D", "main")
    info = inspect_merge(repo, merge, target_branch="pr", root_branch="main")
    assert info is not None
    assert info.merged_from == info.parents[1][:8]
