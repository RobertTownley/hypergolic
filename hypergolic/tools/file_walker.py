"""Walk files respecting gitignore, hidden-file, and skip-dir rules."""

import fnmatch
from pathlib import Path
from typing import Iterator

from hypergolic.tools.gitignore import collect_ignore_rules

SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".hg", ".svn", "venv", ".venv", ".tox", ".eggs"}


def walk_files(
    root: Path,
    *,
    include_hidden: bool = False,
    file_glob: str | None = None,
    max_depth: int | None = None,
) -> Iterator[Path]:
    """Yield files under *root*, skipping ignored/hidden entries."""
    rules = collect_ignore_rules(root)

    def _recurse(directory: Path, depth: int) -> Iterator[Path]:
        if max_depth is not None and depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except PermissionError:
            return

        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                if rules.is_ignored(entry):
                    continue
                yield from _recurse(entry, depth + 1)
            elif entry.is_file():
                if rules.is_ignored(entry):
                    continue
                if file_glob and not fnmatch.fnmatch(entry.name, file_glob):
                    continue
                yield entry

    yield from _recurse(root, 1)
