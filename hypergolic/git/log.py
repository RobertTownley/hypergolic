"""Git log and commit detail."""

from pathlib import Path

from hypergolic.git.commands import git_repo_root, run_git_command
from hypergolic.git.schemas import (
    GitCommitDetailResponse,
    GitLogEntry,
    GitLogResponse,
)


def get_git_commit_detail(
    commit_hash: str, repo: Path | None = None,
    *, session_id: str = "",
) -> GitCommitDetailResponse:
    """Return metadata + diff for a single commit."""
    repo = repo or git_repo_root()
    sep = "\x1f"
    fmt = sep.join(["%H", "%h", "%an", "%aI", "%s"])
    result = run_git_command(
        "log", f"--format={fmt}", "-1", "--end-of-options", commit_hash,
        cwd=repo,
    )
    parts = result.stdout.strip().split(sep)
    if len(parts) != 5:
        return GitCommitDetailResponse(
            session_id=session_id,
            hash=commit_hash, short_hash=commit_hash[:7],
            author="", date="", message="", diff="",
        )
    diff_result = run_git_command(
        "diff-tree", "-p", "--no-commit-id", "--end-of-options", commit_hash,
        cwd=repo,
    )
    return GitCommitDetailResponse(
        session_id=session_id,
        hash=parts[0], short_hash=parts[1],
        author=parts[2], date=parts[3], message=parts[4],
        diff=diff_result.stdout,
    )


def get_git_log(
    count: int = 50, repo: Path | None = None, *, session_id: str = ""
) -> GitLogResponse:
    """Return the last *count* log entries."""
    repo = repo or git_repo_root()
    sep = "\x1f"
    fmt = sep.join(["%H", "%h", "%an", "%aI", "%s", "%D"])
    result = run_git_command("log", f"--format={fmt}", f"-{count}", cwd=repo)
    entries: list[GitLogEntry] = []
    for line in result.stdout.splitlines():
        parts = line.split(sep)
        if len(parts) != 6:
            continue
        entries.append(GitLogEntry(
            hash=parts[0], short_hash=parts[1],
            author=parts[2], date=parts[3],
            message=parts[4], refs=parts[5],
        ))
    return GitLogResponse(session_id=session_id, entries=entries)
