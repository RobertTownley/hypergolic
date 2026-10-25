"""Git status and numstat parsing."""

from pathlib import Path

from hypergolic.git.commands import git_repo_root, merge_base, run_git_command
from hypergolic.git.schemas import ChangedFile, GitStatusResponse


def _parse_numstat(repo: Path, staged: bool) -> dict[str, tuple[int, int]]:
    """Parse `git diff --numstat` output into {path: (additions, deletions)}."""
    args = ["diff", "--numstat"]
    if staged:
        args.append("--cached")
    result = run_git_command(*args, cwd=repo)
    return _numstat_from_output(result.stdout)


def _numstat_from_output(stdout: str) -> dict[str, tuple[int, int]]:
    stats: dict[str, tuple[int, int]] = {}
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            adds = int(parts[0]) if parts[0] != "-" else 0
            dels = int(parts[1]) if parts[1] != "-" else 0
            stats[parts[2]] = (adds, dels)
    return stats


def _all_changes_against_base(repo: Path, base_branch: str) -> list[ChangedFile]:
    """Return every file that differs between the worktree and *base_branch*.

    Combines committed work on the branch with uncommitted edits in the
    working tree (``git diff <merge-base>`` covers both), plus untracked
    files (folded in via ``--no-index`` numstat would be noisy, so they
    are listed with zero counts). The result is a single flat list — in
    this mode the staged/unstaged distinction is meaningless because the
    diff spans commits.
    """
    base = merge_base(repo, base_branch)
    if base is None:
        return []

    name_status = run_git_command(
        "diff", "--name-status", base, cwd=repo,
    )
    numstat = _numstat_from_output(
        run_git_command("diff", "--numstat", base, cwd=repo).stdout
    )

    changes: list[ChangedFile] = []
    seen: set[str] = set()
    for line in name_status.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0][0]
        filepath = parts[-1]
        adds, dels = numstat.get(filepath, (0, 0))
        changes.append(ChangedFile(
            path=filepath, status=status, staged=False,
            additions=adds, deletions=dels,
        ))
        seen.add(filepath)

    untracked = run_git_command(
        "ls-files", "--others", "--exclude-standard", cwd=repo,
    )
    for filepath in untracked.stdout.splitlines():
        filepath = filepath.strip()
        if filepath and filepath not in seen:
            changes.append(ChangedFile(
                path=filepath, status="?", staged=False,
                additions=0, deletions=0,
            ))

    changes.sort(key=lambda c: c.path)
    return changes


def get_git_status(
    repo: Path | None = None, *, session_id: str = "",
    base_branch: str | None = None,
) -> GitStatusResponse:
    """Return structured git status for a repository.

    ``session_id`` is stamped on the response so the frontend can route
    late-arriving responses to the right per-session cache slot; callers
    that aren't part of a session scope (ad-hoc CLI, unit tests) can
    omit it and get an empty string.

    When ``base_branch`` is provided, ``all_changes`` is populated with
    every file that differs between the worktree and that branch's
    merge-base — i.e. committed branch work plus uncommitted edits. The
    frontend's "All changes" toggle reads this list; the staged/unstaged
    /untracked fields are always populated regardless so the
    "Uncommitted only" view never has to refetch.
    """
    repo = repo or git_repo_root()

    branch_result = run_git_command("branch", "--show-current", cwd=repo)
    branch = branch_result.stdout.strip() or "HEAD"

    ahead = 0
    behind = 0
    ab_result = run_git_command(
        "rev-list", "--left-right", "--count", "@{upstream}...HEAD", cwd=repo,
    )
    if ab_result.returncode == 0:
        parts = ab_result.stdout.strip().split()
        if len(parts) == 2:
            behind = int(parts[0])
            ahead = int(parts[1])

    status_result = run_git_command("status", "--porcelain", "-uall", cwd=repo)
    staged_stats = _parse_numstat(repo, staged=True)
    unstaged_stats = _parse_numstat(repo, staged=False)

    staged: list[ChangedFile] = []
    unstaged: list[ChangedFile] = []
    untracked: list[str] = []

    for line in status_result.stdout.splitlines():
        if len(line) < 4:
            continue
        index_status = line[0]
        worktree_status = line[1]
        filepath = line[3:].strip()
        if " -> " in filepath:
            filepath = filepath.split(" -> ", 1)[1]

        if index_status == "?" and worktree_status == "?":
            untracked.append(filepath)
            continue

        if index_status not in (" ", "?"):
            adds, dels = staged_stats.get(filepath, (0, 0))
            staged.append(ChangedFile(
                path=filepath, status=index_status, staged=True,
                additions=adds, deletions=dels,
            ))

        if worktree_status not in (" ", "?"):
            adds, dels = unstaged_stats.get(filepath, (0, 0))
            unstaged.append(ChangedFile(
                path=filepath, status=worktree_status, staged=False,
                additions=adds, deletions=dels,
            ))

    all_changes: list[ChangedFile] = []
    if base_branch:
        all_changes = _all_changes_against_base(repo, base_branch)

    return GitStatusResponse(
        session_id=session_id,
        branch=branch, ahead=ahead, behind=behind,
        staged=staged, unstaged=unstaged, untracked=untracked,
        all_changes=all_changes,
    )
