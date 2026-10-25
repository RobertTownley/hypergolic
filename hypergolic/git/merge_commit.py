"""What a merge-commit candidate actually changed: its conflict resolutions.

A sync merge of the root branch into a PR branch carries every upstream
commit in ``target..candidate``, yet the merge itself only authored the
conflict resolutions. ``diff-tree --cc`` isolates those; a clean merge has
none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hypergolic.git.commands import run_git_command


@dataclass(frozen=True)
class MergeInfo:
    parents: list[str]
    merged_from: str
    conflict_paths: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.conflict_paths


def parents(repo: Path, sha: str) -> list[str]:
    out = run_git_command("rev-list", "--parents", "-n1", sha, cwd=repo).stdout.split()
    return out[1:]


def is_merge_commit(repo: Path, sha: str) -> bool:
    return len(parents(repo, sha)) > 1


def commit_message(repo: Path, sha: str) -> str:
    return run_git_command("log", "-1", "--format=%B", sha, cwd=repo).stdout.strip()


def conflict_paths(repo: Path, sha: str) -> list[str]:
    out = run_git_command(
        "diff-tree", "--cc", "--no-commit-id", "--name-only", "-M", "-z", sha, cwd=repo,
    ).stdout
    return [p for p in out.split("\0") if p]


def combined_patch(repo: Path, sha: str) -> str:
    return run_git_command("diff-tree", "--cc", "--no-commit-id", "-M", sha, cwd=repo).stdout


def merged_from(repo: Path, sha: str, *, exclude: str, prefer: str | None) -> str:
    out = run_git_command(
        "for-each-ref", "--format=%(refname:short)", f"--contains={sha}",
        "refs/heads", "refs/remotes", cwd=repo,
    ).stdout
    names = [n for n in out.split() if n != exclude and not n.endswith("/HEAD")]
    if prefer in names:
        return prefer
    return names[0] if names else sha[:8]


def inspect_merge(
    repo: Path, sha: str, *, target_branch: str, root_branch: str | None = None,
) -> MergeInfo | None:
    ps = parents(repo, sha)
    if len(ps) < 2:
        return None
    return MergeInfo(
        parents=ps,
        merged_from=merged_from(repo, ps[1], exclude=target_branch, prefer=root_branch),
        conflict_paths=conflict_paths(repo, sha),
    )


def clean_merge_summary(info: MergeInfo, commit_count: int) -> str:
    noun = "commit" if commit_count == 1 else "commits"
    return (
        f"Clean merge of {commit_count} {noun} from {info.merged_from}; "
        "no conflict resolutions"
    )
