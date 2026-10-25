from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import hypergolic.config.settings as settings
from hypergolic.contrib import contrib_path
from hypergolic.harness.project import Project

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App

# Built-in harness prompts ship with the package and are read straight from it
# (no longer copied into ~/.hypergolic).
PROMPTS_DIR = Path(contrib_path("prompts"))


def harness_prompt_fn(app: App) -> str:
    """Return the appropriate harness prompt based on whether user has other projects."""
    user_projects = [p for p in app.projects if p.id != "harness"]
    if not user_projects:
        path = PROMPTS_DIR / "onboarding.md"
    else:
        path = PROMPTS_DIR / "harness.md"
    if not path.exists():
        return ""
    return path.read_text()


def get_builtin_harness_project() -> Project:
    """Return the built-in harness project."""
    return Project(
        id="harness",
        name="My Harness",
        description="Your agent configuration \u2014 tools, skills, prompts, and projects",
        git_root=str(settings.HARNESS_DIR),
        prompt_fn=harness_prompt_fn,
    )
