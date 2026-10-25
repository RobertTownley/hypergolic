"""Shared .gitignore / .ignore rule parsing and matching."""

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path


def find_git_root(path: Path) -> Path | None:
    """Walk up from *path* to find the nearest .git directory."""
    current = path
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


@dataclass
class GitignoreRules:

    _rules: list[tuple[bool, bool, str]] = field(default_factory=list)

    def load_file(self, ignore_file: Path) -> None:
        if not ignore_file.is_file():
            return
        base = ignore_file.parent
        for raw in ignore_file.read_text(errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            anchored = "/" in line.rstrip("/")
            pattern = str(base / line.rstrip("/")) if anchored else line.rstrip("/")
            self._rules.append((negated, anchored, pattern))

    def is_ignored(self, path: Path) -> bool:
        ignored = False
        parts = path.parts
        path_str = str(path)
        for negated, anchored, pattern in self._rules:
            if anchored:
                matched = fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(
                    path_str, pattern + "/*"
                )
            else:
                # Non-anchored patterns match any path component, so a rule
                # like ``node_modules/`` also ignores everything beneath it.
                matched = any(fnmatch.fnmatch(part, pattern) for part in parts)
            if matched:
                ignored = not negated
        return ignored


def collect_ignore_rules(root: Path) -> GitignoreRules:
    rules = GitignoreRules()

    git_root = find_git_root(root)
    search_root = git_root if git_root else root

    ancestors: list[Path] = []
    current = root
    while current != search_root:
        ancestors.append(current)
        current = current.parent
    ancestors.append(search_root)
    ancestors.reverse()

    for directory in ancestors:
        for name in (".gitignore", ".ignore"):
            rules.load_file(directory / name)

    return rules
