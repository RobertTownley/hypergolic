"""Building and re-basing the merge candidate in the host repo.

The candidate is the pushed tree squashed onto the base tip as one commit —
what the gates evaluate and what lands. Everything here is plain object
plumbing (``commit-tree``/``merge-tree``); no checkout is touched.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from hypergolic.git.commands import async_run_git_command, git_checked
from hypergolic.git.merge_commit import commit_message, is_merge_commit


class CandidateError(Exception):
    pass


async def _git(cwd: Path, *args: str) -> str:
    return (await git_checked(cwd, *args, error=CandidateError)).strip()


async def resolve_branch(host_repo: Path, branch: str) -> str | None:
    result = await async_run_git_command(
        "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", cwd=host_repo,
    )
    return result.stdout.strip() if result.returncode == 0 else None


async def is_ancestor(host_repo: Path, ancestor: str, descendant: str) -> bool:
    result = await async_run_git_command(
        "merge-base", "--is-ancestor", ancestor, descendant, cwd=host_repo,
    )
    return result.returncode == 0


async def derive_message(host_repo: Path, base_sha: str, sha: str) -> str:
    """Squash message from the branch's commit subjects (oldest first)."""
    out = await _git(
        host_repo, "log", "--reverse", "--format=%s", f"{base_sha}..{sha}",
    )
    subjects = [line for line in out.splitlines() if line.strip()]
    if not subjects:
        raise CandidateError("No commits to land.")
    return "\n\n".join([subjects[0], *subjects[1:]]) if len(subjects) > 1 else subjects[0]


async def tip_message(host_repo: Path, base_sha: str, sha: str) -> str:
    """Fast-forward lands keep *sha* itself, so a merge commit speaks for itself."""
    if await asyncio.to_thread(is_merge_commit, host_repo, sha):
        return await asyncio.to_thread(commit_message, host_repo, sha)
    return await derive_message(host_repo, base_sha, sha)


async def build_candidate(
    host_repo: Path, *, sha: str, base_sha: str, message: str,
) -> str:
    """One squash commit: the pushed tree, parented on the base tip."""
    tree = await _git(host_repo, "rev-parse", "--verify", f"{sha}^{{tree}}")
    return await _git(host_repo, "commit-tree", tree, "-p", base_sha, "-m", message)


async def rebase_candidate(
    host_repo: Path, *, candidate: str, new_tip: str, message: str,
) -> tuple[str | None, str]:
    """Re-parent *candidate* onto a moved base via a textual three-way merge.

    Returns ``(new_candidate, "")`` on a clean merge, ``(None, reason)`` on
    conflicts — the pushing agent must fetch and merge for real.
    """
    result = await async_run_git_command(
        "merge-tree", "--write-tree", new_tip, candidate, cwd=host_repo,
    )
    if result.returncode != 0:
        return None, (
            "the base moved while gates ran and the merge onto its new tip "
            "has conflicts"
        )
    tree = result.stdout.split()[0]
    return await _git(host_repo, "commit-tree", tree, "-p", new_tip, "-m", message), ""
