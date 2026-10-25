"""In-process registry of harness-pinned sessions and the snapshots they use.

A session dispatched with a ``harness`` pin runs its turns under an App built
from a snapshot of ~/.hypergolic at that sha (see harness_snapshot.py). The
dispatch future lives in memory, so module-level maps are sufficient.
"""
from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Callable

import hypergolic.config.settings as config

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App

_pinned_apps: dict[str, "App"] = {}
_snapshot_users: dict[str, set[str]] = {}  # sha -> sessions claiming it
_snapshot_evict_hooks: list[Callable[[str], object]] = []


def on_snapshot_evict(hook: Callable[[str], object]) -> None:
    _snapshot_evict_hooks.append(hook)


def register_snapshot_use(session_id: str, sha: str) -> None:
    _snapshot_users.setdefault(sha, set()).add(session_id)


def release_harness_snapshots(session_id: str) -> None:
    """Drop *session_id*'s claims and delete pinned-harness checkouts nobody
    references — including orphans from crashed runs. Called whenever a
    session concludes; sessions that never pinned a harness make it a no-op."""
    _pinned_apps.pop(session_id, None)
    for sha in list(_snapshot_users):
        _snapshot_users[sha].discard(session_id)
        if not _snapshot_users[sha]:
            del _snapshot_users[sha]
    root = config.INTERNALS_DIR / "harness_snapshots"
    if not root.is_dir():
        return
    for path in root.iterdir():
        if path.name not in _snapshot_users:
            shutil.rmtree(path, ignore_errors=True)
            for hook in _snapshot_evict_hooks:
                hook(path.name)


def pin_app(session_id: str, app: "App") -> None:
    """Route *session_id*'s turns through *app* (a pinned-harness App)."""
    _pinned_apps[session_id] = app


def pinned_app(session_id: str) -> "App | None":
    return _pinned_apps.get(session_id)


def drop_live_derived_pins() -> list[str]:
    """Forget pins built from the live App (override copies) so the next turn
    rebuilds them against a reloaded App. Sessions that claim a harness
    snapshot keep theirs: those Apps come from a checkout, not the live tree."""
    snapshot_sessions: set[str] = set().union(*_snapshot_users.values()) if _snapshot_users else set()
    dropped = [sid for sid in _pinned_apps if sid not in snapshot_sessions]
    for sid in dropped:
        del _pinned_apps[sid]
    return dropped
