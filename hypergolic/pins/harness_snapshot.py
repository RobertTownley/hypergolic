"""Build the user's harness config at an arbitrary git sha as an isolated App.

A harness snapshot is a materialized worktree of ~/.hypergolic at a specific
commit: a shared clone under INTERNALS_DIR/harness_snapshots/<sha>. Building
an App needs real files on disk — main.py is exec'd, prompts and skills are
read by path — and the App keeps reading from its snapshot while it serves
pinned sessions. Snapshots are claimed by the dispatching session and
swept at its conclusion (see pins/runtime.py).

Isolation: harness modules already cached by the live-server load are hidden
from sys.modules during the exec so the snapshot's code resolves against its
own checkout, then restored. Known non-atomic windows: the exec isn't guarded
against concurrent imports on other threads, and the sweep's check-then-rmtree
can race a claim reusing an orphan dir. Loads are rare and fast; harden if it
ever bites.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import hypergolic.config.settings as config
from hypergolic.cli.harness_loader import evict_harness_modules, finalize_app, load_harness_app
from hypergolic.pins.runtime import on_snapshot_evict
from hypergolic.git.commands import run_git_command
from hypergolic.harness.app.core import App

_cache: dict[str, App] = {}
on_snapshot_evict(lambda sha: _cache.pop(sha, None))


def snapshot_harness_app(sha: str) -> App:
    if sha not in _cache:
        app = _load_isolated(_checkout(sha))
        finalize_app(app)
        _cache[sha] = app
    return _cache[sha]


def _checkout(sha: str) -> Path:
    dest = config.INTERNALS_DIR / "harness_snapshots" / sha
    if not (dest / "main.py").exists():
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        run_git_command(
            "clone", "--quiet", "--shared", "--no-checkout",
            str(config.HARNESS_DIR), str(dest), check=True,
        )
        run_git_command("checkout", "--quiet", sha, cwd=dest, check=True)
    return dest


def _load_isolated(harness_dir: Path) -> App:
    """Exec the pinned main.py with live-harness modules shadowed.

    Live-harness entries leave sys.modules for the exec and come back after;
    modules the pinned code imported from its checkout are evicted. First-time
    imports of anything else (stdlib, hypergolic) stay cached as usual.
    """
    saved_path = list(sys.path)
    shadowed = evict_harness_modules(config.HARNESS_DIR)
    try:
        return load_harness_app(harness_dir)
    finally:
        sys.path[:] = saved_path
        evict_harness_modules(harness_dir)
        sys.modules.update(shadowed)
