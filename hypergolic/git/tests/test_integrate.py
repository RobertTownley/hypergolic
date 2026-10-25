"""Tests for hypergolic.git.integrate (branch advance CAS)."""
from __future__ import annotations

from pathlib import Path

import pytest

from hypergolic.git.integrate import advance_branch, checkout_blocker
from tests.helpers.git import commit_file, run_git

pytestmark = pytest.mark.timeout(15)


def _sha(repo: Path, rev: str = "HEAD") -> str:
    return run_git(repo, "rev-parse", rev).stdout.strip()


def _bare_with_commit(tmp_path: Path, repo: Path) -> Path:
    """A bare copy of *repo* so no checkout sits on main (pure update-ref path)."""
    import subprocess
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "clone", "--quiet", "--bare", str(repo), str(bare)],
                   check=True, capture_output=True)
    return bare


async def test_advance_moves_ref_when_cas_holds(repo: Path, tmp_path):
    commit_file(repo, "x.txt", "x\n", "work")
    new = _sha(repo, "main")
    run_git(repo, "update-ref", "refs/heads/main", "main~1")
    bare = _bare_with_commit(tmp_path, repo)
    run_git(bare, "fetch", str(repo), f"+{new}:refs/tmp/new")

    ok, detail = await advance_branch(
        base_branch="main", old_base_sha=_sha(bare, "main"), new_commit=new, cwd=bare,
    )
    assert ok and detail == new
    assert _sha(bare, "main") == new


async def test_advance_rejects_when_base_moved(repo: Path, tmp_path):
    commit_file(repo, "x.txt", "x\n", "work")
    old = _sha(repo, "main~1")
    new = _sha(repo, "main")
    bare = _bare_with_commit(tmp_path, repo)  # bare main == new already

    ok, detail = await advance_branch(
        base_branch="main", old_base_sha=old, new_commit=new, cwd=bare,
    )
    # CAS expected old but the ref is at new: update-ref refuses.
    assert not ok and "moved" in detail


async def test_advance_fast_forwards_a_checkout(repo: Path, tmp_path):
    """When some worktree has main checked out, advance goes through ff merge
    so the working files move too."""
    ws = tmp_path / "co"
    import subprocess
    subprocess.run(["git", "clone", "--quiet", str(repo), str(ws)],
                   check=True, capture_output=True)
    run_git(ws, "config", "user.email", "t@t")
    run_git(ws, "config", "user.name", "t")
    commit_file(repo, "y.txt", "y\n", "host work")  # repo checkout is on main
    old = _sha(repo, "main~1")
    new = _sha(repo, "main")
    run_git(repo, "update-ref", "refs/heads/main", old)

    ok, detail = await advance_branch(
        base_branch="main", old_base_sha=old, new_commit=new, cwd=repo,
    )
    assert ok
    assert _sha(repo, "main") == new
    assert (repo / "y.txt").exists()


async def test_blocker_names_dirty_files_the_commit_changes(repo: Path):
    old = _sha(repo, "main")
    commit_file(repo, "y.txt", "y\n", "work")
    commit_file(repo, "z.txt", "z\n", "more")
    new = _sha(repo, "main")
    run_git(repo, "update-ref", "refs/heads/main", old)
    run_git(repo, "reset", "--soft", old)
    run_git(repo, "reset", "-q")
    (repo / "z.txt").unlink()

    blocked = await checkout_blocker(
        base_branch="main", base_sha=old, new_commit=new, cwd=repo,
    )
    assert blocked is not None and "y.txt" in blocked


async def test_blocker_allows_a_clean_checkout(repo: Path):
    old = _sha(repo, "main")
    commit_file(repo, "y.txt", "y\n", "work")
    new = _sha(repo, "main")
    run_git(repo, "update-ref", "refs/heads/main", old)
    run_git(repo, "reset", "--hard", "-q", old)

    assert await checkout_blocker(
        base_branch="main", base_sha=old, new_commit=new, cwd=repo,
    ) is None
