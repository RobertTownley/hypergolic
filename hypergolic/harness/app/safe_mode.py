from __future__ import annotations

from typing import TYPE_CHECKING

from hypergolic.contrib.roles.registry import ALL_CONTRIB_ROLES
from hypergolic.contrib.skills.registry import ALL_CONTRIB_SKILLS
from hypergolic.contrib.tools.registry import UNIVERSAL_TOOLS

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App


def enter_safe_mode(app: App) -> None:
    app.projects = []
    app.roles = list(ALL_CONTRIB_ROLES)
    app.workflows = []
    app.tools = list(UNIVERSAL_TOOLS)
    app.skills = list(ALL_CONTRIB_SKILLS)
