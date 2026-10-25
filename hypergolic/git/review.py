"""Aggregate payload for the merge-review UI: commits + per-file patches vs base."""

from pathlib import Path
from collections.abc import Sequence
from typing import Literal

from hypergolic.git.commands import merge_base, run_git_command
from hypergolic.git.merge_commit import inspect_merge
from hypergolic.git.schemas import GitLogEntry, GitReviewResponse, MergeCandidate, ReviewFile

ReviewView = Literal["merge", "range"]


def _log_entries(repo: Path, rev_range: str) -> list[GitLogEntry]:
    sep = "\x1f"
    fmt = sep.join(["%H", "%h", "%an", "%aI", "%s", "%D"])
    result = run_git_command("log", f"--format={fmt}", rev_range, cwd=repo)
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
    return entries


def _rev_count(repo: Path, rev_range: str) -> int:
    result = run_git_command("rev-list", "--count", rev_range, cwd=repo)
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def _name_status(
    repo: Path, base: str, head: str | None = None, scope: Sequence[str] = (),
) -> list[tuple[str, str, str | None]]:
    """Return (status, path, old_path) per changed file, rename-aware."""
    result = run_git_command(
        "diff", "--name-status", "-M", "-z", base, *([head] if head else []), *scope, cwd=repo,
    )
    tokens = [t for t in result.stdout.split("\0") if t]
    out: list[tuple[str, str, str | None]] = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        if status.startswith(("R", "C")) and i + 2 < len(tokens):
            out.append((status[0], tokens[i + 2], tokens[i + 1]))
            i += 3
        elif i + 1 < len(tokens):
            out.append((status[0], tokens[i + 1], None))
            i += 2
        else:
            break
    return out


def _numstat(
    repo: Path, base: str, head: str | None = None, scope: Sequence[str] = (),
) -> dict[str, tuple[int, int]]:
    result = run_git_command(
        "diff", "--numstat", "-M", "-z", base, *([head] if head else []), *scope, cwd=repo,
    )
    stats: dict[str, tuple[int, int]] = {}
    tokens = [t for t in result.stdout.split("\0") if t]
    i = 0
    while i < len(tokens):
        parts = tokens[i].split("\t")
        if len(parts) != 3:
            i += 1
            continue
        adds, dels, path = parts
        if path == "":
            # Rename: numstat -z emits "adds\tdels\t" then old and new paths
            # as separate NUL-terminated tokens.
            if i + 2 < len(tokens):
                stats[tokens[i + 2]] = (_int(adds), _int(dels))
            i += 3
        else:
            stats[path] = (_int(adds), _int(dels))
            i += 1
    return stats


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0  # binary files report "-"


def _split_patches(full_diff: str) -> list[str]:
    patches: list[str] = []
    current: list[str] = []
    for line in full_diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                patches.append("".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        patches.append("".join(current))
    return patches


def collect_changed_files(
    repo: Path, base: str, head: str | None = None, paths: list[str] | None = None,
) -> list[ReviewFile]:
    """Per-file patches between *base* and the worktree (or *head* when given)."""
    if paths is not None and not paths:
        return []
    scope: Sequence[str] = ["--", *paths] if paths else ()
    entries = _name_status(repo, base, head, scope)
    stats = _numstat(repo, base, head, scope)
    full_diff = run_git_command(
        "diff", "-M", base, *([head] if head else []), *scope, cwd=repo,
    ).stdout
    patches = _split_patches(full_diff)

    files: list[ReviewFile] = []
    for idx, (status, path, old_path) in enumerate(entries):
        adds, dels = stats.get(path, (0, 0))
        files.append(ReviewFile(
            path=path,
            old_path=old_path,
            status=status,
            additions=adds,
            deletions=dels,
            patch=patches[idx] if idx < len(patches) else "",
        ))
    return files


def get_git_review(
    repo: Path, base_branch: str, branch: str, *, session_id: str = "",
) -> GitReviewResponse:
    base = merge_base(repo, base_branch) or base_branch
    files = collect_changed_files(repo, base)

    return GitReviewResponse(
        session_id=session_id,
        branch=branch,
        base_branch=base_branch,
        merge_base=base,
        ahead=_rev_count(repo, f"{base}..HEAD"),
        behind=_rev_count(repo, f"HEAD..{base_branch}"),
        commits=_log_entries(repo, f"{base}..HEAD"),
        files=files,
    )


def get_candidate_review(
    repo: Path, base_sha: str, head_sha: str, base_branch: str, *,
    session_id: str = "", root_branch: str | None = None, view: ReviewView = "merge",
) -> GitReviewResponse:
    """Review payload for a landing candidate: the exact host-side span that
    lands if approved, independent of any workspace state.

    A merge-commit candidate defaults to its own contribution — the files it
    resolved conflicts in, diffed against the branch it lands on — because the
    merged-in commits were already reviewed where they came from. ``view="range"``
    shows the whole span anyway.
    """
    info = inspect_merge(repo, head_sha, target_branch=base_branch, root_branch=root_branch)
    merge = None
    paths = None
    if info is not None:
        merge = MergeCandidate(
            parents=info.parents, merged_from=info.merged_from,
            merged_count=_rev_count(repo, f"{base_sha}..{info.parents[1]}"),
            conflict_paths=info.conflict_paths, view=view,
        )
        if view == "merge":
            paths = info.conflict_paths
    return GitReviewResponse(
        session_id=session_id,
        branch=head_sha[:12],
        base_branch=base_branch,
        merge_base=base_sha,
        ahead=_rev_count(repo, f"{base_sha}..{head_sha}"),
        behind=_rev_count(repo, f"{head_sha}..{base_branch}"),
        commits=_log_entries(repo, f"{base_sha}..{head_sha}"),
        files=collect_changed_files(repo, base_sha, head_sha, paths),
        merge=merge,
    )
