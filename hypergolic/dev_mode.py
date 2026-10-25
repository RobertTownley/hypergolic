"""Dev-mode detection, shared by the CLI, launcher, and dev-only tools."""
from __future__ import annotations

import os
from pathlib import Path


def is_dev_mode() -> bool:
    return os.environ.get("HYPERGOLIC_DEV_MODE", "").lower() in ("1", "true", "yes")


def source_root() -> Path | None:
    """The hypergolic repo root when running from a source checkout, else None."""
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "pyproject.toml").exists():
        return candidate
    return None
