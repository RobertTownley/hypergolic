"""Tests for hypergolic.gates.candidate against real repos."""
from __future__ import annotations

from pathlib import Path

import pytest

from hypergolic.gates.candidate import (
    CandidateError,
    build_candidate,
    derive_message,
    is_ancestor,
    rebase_candidate,
    resolve_branch,
)
from tests.helpers.git import clone_workspace, commit_file, run_git

pytestmark = pytest.mark.timeout(15)


def _sha(repo: Path, rev: str = "HEAD") -> str:
    return run_git(repo, "rev-parse", rev).stdout.strip()


@pytest.fixture
def ws(repo, tmp_path):
    ws = tmp_path / "ws"
    clone_workspace(repo, ws, "work")
    return ws


async def test_resolve_and_ancestry(repo: Path, ws: Path):
    base = _sha(repo, "main")
    assert await resolve_branch(repo, "main") == base
    assert await resolve_branch(repo, "nope") is None

    commit_file(ws, "a.txt", "a\n", "add a")
    run_git(repo, "fetch", str(ws), "work:work")
    assert await is_ancestor(repo, base, _sha(repo, "work"))
    assert not await is_ancestor(repo, _sha(repo, "work"), base)


async def test_derive_message_joins_subjects(repo: Path, ws: Path):
    commit_file(ws, "a.txt", "a\n", "first step")
    commit_file(ws, "b.txt", "b\n", "second step")
    run_git(repo, "fetch", str(ws), "work:work")
    msg = await derive_message(repo, _sha(repo, "main"), _sha(repo, "work"))
    assert msg == "first step\n\nsecond step"

    with pytest.raises(CandidateError, match="No commits"):
        await derive_message(repo, _sha(repo, "main"), _sha(repo, "main"))


async def test_build_candidate_squashes_onto_base(repo: Path, ws: Path):
    commit_file(ws, "a.txt", "a\n", "add a")
    commit_file(ws, "b.txt", "b\n", "add b")
    run_git(repo, "fetch", str(ws), "work:work")
    base = _sha(repo, "main")

    cand = await build_candidate(repo, sha=_sha(repo, "work"), base_sha=base, message="squash!")
    assert run_git(repo, "rev-parse", f"{cand}^").stdout.strip() == base
    assert run_git(repo, "log", "-1", "--format=%s", cand).stdout.strip() == "squash!"
    assert run_git(repo, "rev-parse", f"{cand}^{{tree}}").stdout.strip() == \
        run_git(repo, "rev-parse", "work^{tree}").stdout.strip()


async def test_rebase_candidate_clean_and_conflicting(repo: Path, ws: Path):
    base = _sha(repo, "main")
    commit_file(ws, "a.txt", "a\n", "add a")
    run_git(repo, "fetch", str(ws), "work:work")
    cand = await build_candidate(repo, sha=_sha(repo, "work"), base_sha=base, message="add a")

    commit_file(repo, "other.txt", "other\n", "unrelated")
    new_tip = _sha(repo, "main")
    rebased, reason = await rebase_candidate(repo, candidate=cand, new_tip=new_tip, message="add a")
    assert rebased and not reason
    assert run_git(repo, "rev-parse", f"{rebased}^").stdout.strip() == new_tip
    files = run_git(repo, "ls-tree", "--name-only", rebased).stdout
    assert "a.txt" in files and "other.txt" in files

    commit_file(repo, "a.txt", "conflict\n", "host writes a.txt")
    rebased, reason = await rebase_candidate(
        repo, candidate=cand, new_tip=_sha(repo, "main"), message="add a",
    )
    assert rebased is None and "conflict" in reason


async def test_tip_message_uses_the_merge_commits_own_message(repo: Path):
    from hypergolic.gates.candidate import tip_message
    from tests.helpers.git import sync_merge

    pr_tip, merge = sync_merge(repo)
    assert (await tip_message(repo, pr_tip, merge)).startswith("Merge branch 'main' into pr")
    assert "main one" not in await tip_message(repo, pr_tip, merge)
    plain = _sha(repo, "main")
    assert await tip_message(repo, _sha(repo, "main~2"), plain) == "main one\n\nmain two"
