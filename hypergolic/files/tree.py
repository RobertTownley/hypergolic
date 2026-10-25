"""Build a file tree with git status annotations."""

import subprocess
from pathlib import Path

from hypergolic.files.schemas import FileNode
from hypergolic.git.commands import git_repo_root

_SKIP_DIRS = {"node_modules", "__pycache__"}


def _git_status_map(repo_root: Path) -> dict[str, str]:
    """Run `git status --porcelain` and return {rel_path: status_code}."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            capture_output=True, text=True, check=True, cwd=repo_root,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    status_map: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        filepath = line[3:].strip()
        if " -> " in filepath:
            filepath = filepath.split(" -> ", 1)[1]
        status_map[filepath] = xy.strip()
    return status_map


def _git_ignored_set(repo_root: Path) -> set[str]:
    """Return the set of git-ignored paths (relative to *repo_root*)."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--directory"],
            capture_output=True, text=True, check=True, cwd=repo_root,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()

    ignored: set[str] = set()
    for line in result.stdout.splitlines():
        entry = line.strip().rstrip("/")
        if entry:
            ignored.add(entry)
    return ignored


def _is_ignored(rel: str, ignored_set: set[str]) -> bool:
    """Check if *rel* is in or under any entry in *ignored_set*."""
    return rel in ignored_set or any(
        rel.startswith(ign + "/") for ign in ignored_set
    )


def _dir_aggregate_status(dir_rel: str, status_map: dict[str, str]) -> str | None:
    """Derive a single status for a directory from its children."""
    prefix = dir_rel + "/"
    statuses = {v for k, v in status_map.items() if k.startswith(prefix)}
    if not statuses:
        return None
    if "M" in statuses or "MM" in statuses or "AM" in statuses:
        return "M"
    if "A" in statuses:
        return "A"
    if "??" in statuses:
        return "??"
    return next(iter(statuses))


def _build_tree(
    directory: Path,
    repo_root: Path,
    status_map: dict[str, str],
    ignored_set: set[str],
) -> list[FileNode]:
    """Recursively build FileNode tree for *directory*."""
    nodes: list[FileNode] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return nodes

    for entry in entries:
        if entry.name.startswith("."):
            continue

        rel = str(entry.relative_to(repo_root))
        ignored = _is_ignored(rel, ignored_set)

        if entry.is_dir():
            if entry.name in _SKIP_DIRS:
                continue
            children = _build_tree(entry, repo_root, status_map, ignored_set)
            git_status = "ignored" if ignored else _dir_aggregate_status(rel, status_map)
            nodes.append(FileNode(
                name=entry.name, path=rel, is_dir=True,
                git_status=git_status, children=children,
            ))
        else:
            git_status = "ignored" if ignored else status_map.get(rel)
            nodes.append(FileNode(
                name=entry.name, path=rel, is_dir=False,
                git_status=git_status,
            ))

    return nodes


def build_file_tree(repo_root: Path | None = None) -> list[FileNode]:
    """Build the full file tree for a repository."""
    root = repo_root or git_repo_root()
    status_map = _git_status_map(root)
    ignored_set = _git_ignored_set(root)
    return _build_tree(root, root, status_map, ignored_set)


def get_repo_root(repo_root: Path | None = None) -> str:
    """Return the repo root as a string."""
    return str(repo_root or git_repo_root())
