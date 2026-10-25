"""Session workspace naming helpers.

Workspaces live at ``<worktrees_root>/<project_id>/<sanitized_branch>/`` on
branch ``<base_branch>-<session_id>``. The dir is a plain bind-mount target:
the repo itself is cloned *inside* the session's sandbox (see
docs/sandbox-lifecycle.md), so nothing here touches git.
"""

from __future__ import annotations

from pathlib import Path

from hypergolic.config.settings import settings

_UNSAFE_PATH_CHARS = str.maketrans({
    "/": "-",
    "\\": "-",
    ":": "-",
    "*": "-",
    "?": "-",
    '"': "-",
    "<": "-",
    ">": "-",
    "|": "-",
    " ": "-",
})


def sanitize_branch_for_path(branch: str) -> str:
    """Replace path-hostile characters (slashes etc.) with ``-``."""
    return branch.translate(_UNSAFE_PATH_CHARS)


def worktrees_root() -> Path:
    return Path(settings.HYPERGOLIC_WORKTREES_ROOT)


def worktree_branch_name(session_id: str, base_branch: str) -> str:
    """``<base_branch>-<session_id>``; composes naturally for subagents."""
    return f"{base_branch}-{session_id}"


def worktree_path_for(project_id: str, branch: str) -> Path:
    return worktrees_root() / project_id / sanitize_branch_for_path(branch)
