"""Inline changes payload: per-file patches honoring the diff-mode toggle."""

from pathlib import Path
from typing import Literal

from hypergolic.git.commands import merge_base, run_git_command
from hypergolic.git.review import collect_changed_files
from hypergolic.git.schemas import GitChangesResponse, ReviewFile


def _untracked_paths(repo: Path) -> list[str]:
    out = run_git_command("ls-files", "--others", "--exclude-standard", cwd=repo)
    return [p.strip() for p in out.stdout.splitlines() if p.strip()]


def _untracked_file(repo: Path, path: str) -> ReviewFile:
    # --no-index exits 1 when files differ; that's the normal case here.
    patch = run_git_command(
        "diff", "--no-index", "--", "/dev/null", path, cwd=repo,
    ).stdout
    adds = sum(
        1 for ln in patch.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    )
    return ReviewFile(path=path, status="?", additions=adds, deletions=0, patch=patch)


def get_git_changes(
    repo: Path,
    mode: Literal["all", "uncommitted"],
    base_branch: str | None,
    *,
    session_id: str = "",
) -> GitChangesResponse:
    if mode == "all" and base_branch:
        base = merge_base(repo, base_branch) or base_branch
    else:
        base = "HEAD"
    files = collect_changed_files(repo, base)
    seen = {f.path for f in files}
    files += [_untracked_file(repo, p) for p in _untracked_paths(repo) if p not in seen]
    files.sort(key=lambda f: f.path)
    return GitChangesResponse(session_id=session_id, files=files)
