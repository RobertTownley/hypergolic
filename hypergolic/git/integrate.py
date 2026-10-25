"""Advancing a host base branch to a landed commit.

The land pipeline (:mod:`hypergolic.gates`) builds the squash candidate
itself; what remains is moving the branch — a compare-and-swap
``update-ref`` (or ``--ff-only`` merge when some checkout is on the base),
so the user's own checkout can be on any branch, clean or dirty.
"""

from __future__ import annotations

import logging
from pathlib import Path

from hypergolic.git.commands import async_run_git_command

logger = logging.getLogger(__name__)


async def worktree_checked_out_on(branch: str, cwd: Path) -> Path | None:
    """Return the working-tree path where *branch* is checked out, if any."""
    result = await async_run_git_command("worktree", "list", "--porcelain", cwd=cwd)
    if result.returncode != 0:
        return None
    target = f"refs/heads/{branch}"
    current: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current = line[len("worktree "):].strip()
        elif line.startswith("branch ") and line[len("branch "):].strip() == target:
            return Path(current) if current else None
    return None


async def checkout_blocker(
    *, base_branch: str, base_sha: str, new_commit: str, cwd: Path,
) -> str | None:
    checkout = await worktree_checked_out_on(base_branch, cwd)
    if checkout is None:
        return None
    changed = await async_run_git_command(
        "diff", "--name-only", "-z", base_sha, new_commit, cwd=cwd,
    )
    status = await async_run_git_command(
        "status", "--porcelain", "-z", "--no-renames", cwd=checkout,
    )
    dirty = {entry[3:] for entry in status.stdout.split("\0") if entry}
    overlap = sorted(dirty & set(filter(None, changed.stdout.split("\0"))))
    if not overlap:
        return None
    return (
        f"the `{base_branch}` checkout at {checkout} has uncommitted changes to "
        f"files this commit changes: {', '.join(overlap)}. Commit or revert "
        "them there, or leave them out of this commit, then push again."
    )


async def advance_branch(
    *, base_branch: str, old_base_sha: str, new_commit: str, cwd: Path,
) -> tuple[bool, str]:
    """Move ``refs/heads/base_branch`` from *old_base_sha* to *new_commit*.

    The CAS on *old_base_sha* rejects any base advance since the candidate
    was built; the caller decides what a stale base means (``on_stale_base``).
    """
    checkout = await worktree_checked_out_on(base_branch, cwd)
    if checkout is not None:
        ff = await async_run_git_command("merge", "--ff-only", new_commit, cwd=checkout)
        if ff.returncode != 0:
            return False, (
                f"Could not fast-forward the `{base_branch}` checkout at "
                f"{checkout} — the base may have advanced, or that checkout "
                "has conflicting uncommitted changes:\n"
                f"{ff.stderr.strip() or ff.stdout.strip()}"
            )
    else:
        upd = await async_run_git_command(
            "update-ref", f"refs/heads/{base_branch}", new_commit, old_base_sha,
            cwd=cwd,
        )
        if upd.returncode != 0:
            return False, (
                f"`{base_branch}` moved while gates ran:\n"
                f"{upd.stderr.strip() or upd.stdout.strip()}"
            )
    return True, new_commit
