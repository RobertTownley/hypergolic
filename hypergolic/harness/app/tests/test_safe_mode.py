"""Tests for safe mode tool/role configuration."""

from hypergolic.contrib.roles.registry import ALL_CONTRIB_ROLES
from hypergolic.contrib.tools.registry import UNIVERSAL_TOOLS
from hypergolic.harness.app.core import App
from hypergolic.harness.app.safe_mode import enter_safe_mode


def test_safe_mode_sets_universal_tools():
    app = App()
    enter_safe_mode(app)
    tool_ids = {t.id for t in app.tools}
    universal_ids = {t.id for t in UNIVERSAL_TOOLS}
    assert tool_ids == universal_ids


def test_safe_mode_sets_all_base_roles():
    app = App()
    enter_safe_mode(app)
    role_ids = {r.id for r in app.roles}
    expected_ids = {r.id for r in ALL_CONTRIB_ROLES}
    assert role_ids == expected_ids


def test_safe_mode_clears_projects_and_workflows():
    app = App()
    enter_safe_mode(app)
    assert app.projects == []
    assert app.workflows == []
