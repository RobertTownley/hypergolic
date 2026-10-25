from __future__ import annotations

from pathlib import Path

import pytest

from hypergolic.git.review import get_git_review
from tests.helpers.git import copy_repo, init_repo, run_git, sync_merge

pytestmark = pytest.mark.timeout(15)


@pytest.fixture(scope="module")
def _seeded(tmp_path_factory) -> Path:
    r = tmp_path_factory.mktemp("review") / "repo"
    init_repo(r)
    (r / "keep.txt").write_text("keep\n")
    (r / "old.txt").write_text("line1\nline2\nline3\nline4\nline5\n")
    (r / "gone.txt").write_text("bye\n")
    run_git(r, "add", "-A")
    run_git(r, "commit", "-m", "seed files")
    run_git(r, "checkout", "-b", "feat")
    return r


@pytest.fixture
def repo(_seeded: Path, tmp_path: Path) -> Path:
    return copy_repo(_seeded, tmp_path / "repo")


def test_no_changes(repo: Path):
    review = get_git_review(repo, "main", "feat", session_id="s1")
    assert review.session_id == "s1"
    assert review.branch == "feat"
    assert review.ahead == 0
    assert review.commits == []
    assert review.files == []


def test_commits_files_and_patches(repo: Path):
    (repo / "new.txt").write_text("hello\n")
    (repo / "keep.txt").write_text("keep\nmore\n")
    (repo / "gone.txt").unlink()
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "first change")
    (repo / "new.txt").write_text("hello\nworld\n")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "second change")

    review = get_git_review(repo, "main", "feat")
    assert review.ahead == 2
    assert [c.message for c in review.commits] == ["second change", "first change"]

    by_path = {f.path: f for f in review.files}
    assert set(by_path) == {"new.txt", "keep.txt", "gone.txt"}
    assert by_path["new.txt"].status == "A"
    assert by_path["new.txt"].additions == 2
    assert by_path["gone.txt"].status == "D"
    assert by_path["keep.txt"].status == "M"
    assert "+world" in by_path["new.txt"].patch
    assert "+more" in by_path["keep.txt"].patch
    assert "-bye" in by_path["gone.txt"].patch


def test_rename_detected(repo: Path):
    run_git(repo, "mv", "old.txt", "renamed.txt")
    run_git(repo, "commit", "-m", "rename")

    review = get_git_review(repo, "main", "feat")
    by_path = {f.path: f for f in review.files}
    assert "renamed.txt" in by_path
    assert by_path["renamed.txt"].status == "R"
    assert by_path["renamed.txt"].old_path == "old.txt"


def test_uncommitted_changes_included(repo: Path):
    (repo / "keep.txt").write_text("keep\nuncommitted\n")
    review = get_git_review(repo, "main", "feat")
    assert [f.path for f in review.files] == ["keep.txt"]
    assert "+uncommitted" in review.files[0].patch


def test_behind_counts_base_commits(repo: Path):
    run_git(repo, "checkout", "main")
    (repo / "base-only.txt").write_text("base\n")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "base moves on")
    run_git(repo, "checkout", "feat")

    review = get_git_review(repo, "main", "feat")
    assert review.behind == 1
    assert review.ahead == 0
    assert review.files == []


def _candidate(repo: Path, **kw):
    from hypergolic.git.review import get_candidate_review

    pr_tip, merge = sync_merge(repo, conflict=kw.pop("conflict", False))
    return get_candidate_review(repo, pr_tip, merge, "pr", root_branch="main", **kw)


def test_clean_merge_candidate_shows_no_files_but_lists_commits(repo: Path):
    review = _candidate(repo)
    assert review.merge is not None
    assert review.merge.merged_from == "main"
    assert review.merge.merged_count == 2
    assert review.merge.conflict_paths == []
    assert review.merge.view == "merge"
    assert review.files == []
    assert [c.message for c in review.commits][1:] == ["main two", "main one"]


def test_conflicting_merge_candidate_shows_only_resolved_files(repo: Path):
    review = _candidate(repo, conflict=True)
    assert review.merge is not None
    assert [f.path for f in review.files] == ["f.txt"]
    assert "+resolved" in review.files[0].patch
    assert "-pr side" in review.files[0].patch


def test_range_view_of_a_merge_candidate_shows_everything(repo: Path):
    review = _candidate(repo, view="range")
    assert review.merge is not None
    assert review.merge.view == "range"
    assert {f.path for f in review.files} == {"m1.txt", "m2.txt"}


def test_plain_candidate_has_no_merge_info(repo: Path):
    from hypergolic.git.review import get_candidate_review

    base = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "keep.txt").write_text("keep\nmore\n")
    run_git(repo, "commit", "-qam", "edit")
    head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    review = get_candidate_review(repo, base, head, "main")
    assert review.merge is None
    assert [f.path for f in review.files] == ["keep.txt"]
