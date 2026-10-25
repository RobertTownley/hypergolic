"""The user's harness repo (``~/.hypergolic``) and per-session /harness clones.

The harness is edited through the same discipline as project code: each
sandboxed session gets an in-container clone of the harness repo — working
files bind-mounted rw at ``/harness`` from :func:`harness_workspace_path`,
gitdir in the session's ``/var/git`` volume — provisioned alongside the app
clone (:mod:`hypergolic.sandbox.manager.repo_provision`). Changes land on the
harness's main branch only through gated ``git push origin main`` from the
/harness clone.

A ``~/.hypergolic`` that isn't a git repo gets no clone (and an empty
/harness): editability is the point of the mount, and an unversioned config
edited in place would have no review or rollback path.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from hypergolic.git.commands import run_git_command
import hypergolic.config.settings as config
from hypergolic.cli.init_cmd import setup_gitignore

logger = logging.getLogger(__name__)

#: The session's harness branch gets a suffix beyond the project convention
#: because a session *on the harness project itself* clones the same host
#: repo twice (/app and /harness); distinct names keep host-side
#: ``refs/hypergolic`` fetches unambiguous.
HARNESS_BRANCH_SUFFIX = "-harness"


def _harness_dir() -> Path:
    return config.HARNESS_DIR


def harness_workspace_path(session_id: str) -> Path:
    """Host source dir of the session's /harness bind mount (files only; the
    gitdir lives in the sandbox's volume)."""
    return config.session_internals_dir(session_id) / "harness"


def remove_session_workspaces(session_id: str) -> None:
    """Delete the session's bind-source dirs (/harness and /shared files;
    gitdirs die with the sandbox volume) and its quarantine repos.
    Best-effort."""
    from hypergolic.git.quarantine import delete_session_quarantines

    shutil.rmtree(config.session_internals_dir(session_id), ignore_errors=True)
    delete_session_quarantines(session_id)


def harness_session_branch(worktree_branch: str) -> str:
    return f"{worktree_branch}{HARNESS_BRANCH_SUFFIX}"


def ensure_harness_repo() -> None:
    """Bring ``~/.hypergolic`` under git when it isn't: the /harness clone and
    harness merges need a repo with a commit.

    Heals installs that predate git-controlled harnesses. An existing history
    is never touched — dirty state, odd branches, and detached HEADs belong to
    the user.
    """
    harness = _harness_dir()
    if not harness.exists():
        return
    if not (harness / ".git").exists():
        result = run_git_command("init", "-b", "main", cwd=harness)
        if result.returncode != 0:
            logger.warning("git init failed in %s: %s", harness, result.stderr.strip())
            return
        logger.info("Initialized git repo at %s", harness)
    if run_git_command("rev-parse", "--verify", "HEAD", cwd=harness).returncode == 0:
        return
    # First commit: make sure runtime exhaust (db, worktrees, ...) stays out.
    try:
        setup_gitignore(root_dir=harness)
    except Exception:  # pragma: no cover - defensive
        logger.warning("Could not write harness .gitignore", exc_info=True)
    run_git_command("add", "-A", cwd=harness)
    result = run_git_command("commit", "-m", "Initial harness configuration", cwd=harness)
    if result.returncode != 0:
        logger.warning(
            "Initial harness commit failed (is git user.email configured?): %s",
            result.stderr.strip() or result.stdout.strip(),
        )
    else:
        logger.info("Created initial harness commit in %s", harness)


def harness_base_branch() -> str | None:
    """The branch ``~/.hypergolic`` is checked out on, or None when it isn't a
    usable repo (not git-controlled, detached HEAD, or no commits yet)."""
    harness = _harness_dir()
    if not (harness / ".git").exists():
        return None
    result = run_git_command("rev-parse", "--abbrev-ref", "HEAD", cwd=harness)
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch or branch == "HEAD":
        return None
    result = run_git_command("rev-parse", "--verify", "HEAD", cwd=harness)
    return branch if result.returncode == 0 else None
