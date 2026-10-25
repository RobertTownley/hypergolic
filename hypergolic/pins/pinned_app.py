"""Resolve a harness pin to the App a pinned session should run under."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import hypergolic.config.settings as config
from hypergolic.pins.runtime import register_snapshot_use
from hypergolic.git.commands import run_git_command

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App


def head_sha(repo: Path) -> str:
    result = run_git_command("rev-parse", "HEAD", cwd=repo, check=True)
    return result.stdout.strip()


def snapshot_app_for(pins: dict[str, str], session_id: str) -> "App | None":
    """The harness-snapshot App for a harness pin; None when unpinned or at tip."""
    sha = pins.get("harness")
    if sha is None or sha == head_sha(config.HARNESS_DIR):
        return None
    # Claim before building: the conclude-time orphan sweep deletes any
    # unclaimed checkout, so an unclaimed build window would race it.
    register_snapshot_use(session_id, sha)
    # cycle: harness_snapshot -> cli.harness_loader -> harness.app.core -> contrib
    from hypergolic.pins.harness_snapshot import snapshot_harness_app

    return snapshot_harness_app(sha)
