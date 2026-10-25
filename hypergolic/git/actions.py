"""Git mutating actions: stage, unstage, discard, commit, push, pull."""

from pathlib import Path

from hypergolic.git.commands import git_repo_root, run_git_command


def git_stage(paths: list[str], repo: Path | None = None) -> None:
    repo = repo or git_repo_root()
    run_git_command("add", "--", *paths, cwd=repo, check=True)


def git_unstage(paths: list[str], repo: Path | None = None) -> None:
    repo = repo or git_repo_root()
    run_git_command("reset", "HEAD", "--", *paths, cwd=repo, check=True)


def _classify_paths(
    paths: list[str], repo: Path,
) -> tuple[list[str], list[str]]:
    """Split ``paths`` into (tracked, added-or-untracked).

    Tracked paths (modified/deleted in the worktree relative to the index)
    are reverted with ``git checkout``. Added-or-untracked paths have no
    committed content to restore, so they're removed from the index (if
    staged) and deleted from disk.

    Uses ``git status --porcelain -z`` so paths with spaces or special
    characters are emitted verbatim (no C-quoting).
    """
    result = run_git_command(
        "status", "--porcelain", "-uall", "-z", "--", *paths, cwd=repo,
    )
    # NUL-separated records; a rename record is followed by an extra
    # NUL-separated field (the origin path) which we skip.
    fields = result.stdout.split("\0")
    status: dict[str, str] = {}
    i = 0
    while i < len(fields):
        entry = fields[i]
        if not entry:
            i += 1
            continue
        code, path = entry[:2], entry[3:]
        status[path] = code
        # A rename ('R') consumes the following origin-path field.
        if code and code[0] == "R":
            i += 1
        i += 1

    tracked: list[str] = []
    added_or_untracked: list[str] = []
    for path in paths:
        code = status.get(path, "")
        index_status = code[0] if code else ""
        if code == "??" or index_status == "A":
            added_or_untracked.append(path)
        else:
            tracked.append(path)
    return tracked, added_or_untracked


def git_discard(paths: list[str], repo: Path | None = None) -> None:
    repo = repo or git_repo_root()
    tracked, added_or_untracked = _classify_paths(paths, repo)
    if tracked:
        run_git_command("checkout", "--", *tracked, cwd=repo, check=True)
    if added_or_untracked:
        # Unstage any staged additions so `clean` will remove them,
        # then delete the working-tree copies.
        run_git_command("reset", "-q", "HEAD", "--", *added_or_untracked, cwd=repo)
        run_git_command("clean", "-fd", "--", *added_or_untracked, cwd=repo, check=True)


def get_git_branches(
    repo: Path | None = None, *, session_id: str = ""
) -> dict[str, object]:
    repo = repo or git_repo_root()
    result = run_git_command("branch", cwd=repo)
    branches: list[str] = []
    current = ""
    for line in result.stdout.splitlines():
        name = line.strip().lstrip("* ").strip()
        if name:
            branches.append(name)
            if line.startswith("*"):
                current = name
    return {"session_id": session_id, "branches": branches, "current": current}


def git_checkout(branch: str, repo: Path | None = None) -> str:
    repo = repo or git_repo_root()
    result = run_git_command("checkout", branch, cwd=repo, check=True)
    return result.stdout.strip() or result.stderr.strip()


def git_create_branch(name: str, repo: Path | None = None) -> str:
    repo = repo or git_repo_root()
    result = run_git_command("checkout", "-b", name, cwd=repo, check=True)
    return result.stdout.strip() or result.stderr.strip()
