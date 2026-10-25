"""Git diff operations."""

from pathlib import Path

from hypergolic.git.commands import git_repo_root, merge_base, run_git_command
from hypergolic.git.schemas import GitDiffResponse


def _is_tracked(path: str, repo: Path) -> bool:
    result = run_git_command("ls-files", "--error-unmatch", "--", path, cwd=repo)
    return result.returncode == 0


def get_git_diff(
    path: str | None, staged: bool, repo: Path | None = None,
    *, session_id: str = "", base_branch: str | None = None,
) -> GitDiffResponse:
    """Return the diff for *path* (or the whole repo if None).

    When ``base_branch`` is set the diff is taken against the merge-base
    with that branch (committed branch work + uncommitted edits), backing
    the "All changes" view. Untracked files still fall back to a
    ``--no-index`` diff so brand-new files render. Otherwise the diff is
    the usual working-tree (or ``--cached``) diff.
    """
    repo = repo or git_repo_root()

    if base_branch:
        base = merge_base(repo, base_branch)
        if base is not None:
            args = ["diff", base]
            if path:
                args.extend(["--", path])
            result = run_git_command(*args, cwd=repo)
            diff_text = result.stdout
            if path and not diff_text and not _is_tracked(path, repo):
                diff_text = run_git_command(
                    "diff", "--no-index", "/dev/null", path, cwd=repo,
                ).stdout
            return GitDiffResponse(
                session_id=session_id, path=path or "", diff=diff_text,
            )

    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        args.extend(["--", path])
    result = run_git_command(*args, cwd=repo)
    diff_text = result.stdout
    if path and not diff_text and not staged and not _is_tracked(path, repo):
        new_result = run_git_command(
            "diff", "--no-index", "/dev/null", path, cwd=repo,
        )
        diff_text = new_result.stdout
    return GitDiffResponse(session_id=session_id, path=path or "", diff=diff_text)
