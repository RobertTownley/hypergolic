"""Allowlisted paths for read access outside the project directory.

Paths listed here are readable without requiring user approval even when they
fall outside the current project directory. This drives ``decide_read``, which
the dispatch tool uses to decide whether it may inline a referenced file for a
child session.

Each entry is resolved via Path.expanduser() so ~ is supported.
"""

import hypergolic as hypergolic_pkg
from pathlib import Path


def _hypergolic_source_roots() -> list[str]:
    """Wherever ``from hypergolic import ...`` resolves to is fair game to read.

    For a normal site-packages install this is just the package directory.
    For an editable / dev checkout (parent contains ``pyproject.toml``), the
    repo root is included too so siblings like ``tests/``, ``ui/``, and
    ``pyproject.toml`` are reachable without approval.

    The ``pyproject.toml`` sentinel is a heuristic: any unrelated project
    that places a ``pyproject.toml`` immediately above its ``hypergolic``
    package would also unlock its repo root. We accept that trade-off —
    in a dev install the repo root is exactly the scope we want, and the
    only paths that satisfy the precondition are ones that already imported
    as ``hypergolic`` in the running interpreter.
    """
    pkg_dir = Path(hypergolic_pkg.__file__).resolve().parent
    roots = [str(pkg_dir)]
    repo_root = pkg_dir.parent
    if (repo_root / "pyproject.toml").is_file():
        roots.append(str(repo_root))
    return roots


# Paths (files or directories) readable without approval even when outside the
# project. Directory entries grant access to the entire subtree.
READONLY_ALLOWLIST: list[str] = [
    "~/.hypergolic",
    "~/.aws/config",
    *_hypergolic_source_roots(),
]
