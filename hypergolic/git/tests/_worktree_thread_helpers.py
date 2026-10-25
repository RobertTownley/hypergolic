"""Shared test helpers for the async worktree lifecycle.

Teardown (and creation) now run on daemon threads named
``worktree-teardown-<session_id>`` / ``worktree-create-<session_id>``.
Tests that assert on filesystem or git state after scheduling teardown
must join those threads first — otherwise they race the background
work and flake.
"""

from __future__ import annotations

import threading


def join_worktree_threads(timeout: float = 5.0) -> None:
    """Block until all active worktree background threads finish.

    Safe to call from any test: it only joins threads whose names start
    with the worktree lifecycle prefixes, so unrelated daemon threads
    (uvicorn workers, anyio portals) are left alone.
    """
    for thread in list(threading.enumerate()):
        name = thread.name
        if name.startswith(("worktree-create-", "worktree-teardown-")):
            thread.join(timeout=timeout)
