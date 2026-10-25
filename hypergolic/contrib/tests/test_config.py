"""Ensure the base registries never contain duplicate IDs.

This catches mistakes like a skill appearing in both ALL_CONTRIB_SKILLS
and a role's skills list, or duplicate tool/role IDs across registries.
"""

from hypergolic.contrib.skills.registry import ALL_CONTRIB_SKILLS
from hypergolic.contrib.roles.registry import ALL_CONTRIB_ROLES
from hypergolic.contrib.tools.registry import (
    UNIVERSAL_TOOLS,
)
from hypergolic.harness.app.core import App
from hypergolic.harness.app.validation import validate_app
from hypergolic.contrib.workflows import ALL_CONTRIB_WORKFLOWS


def _build_full_app() -> App:
    app = App()
    app.register_tools(UNIVERSAL_TOOLS)
    app.register_roles(ALL_CONTRIB_ROLES)
    app.register_skills(ALL_CONTRIB_SKILLS)
    return app


def test_no_duplicate_skill_ids():
    """Every skill ID must be unique across all base registries."""
    errors = validate_app(_build_full_app())
    skill_errors = [e for e in errors if "Duplicate skill ID" in e]
    assert skill_errors == [], f"Duplicate skills in base config: {skill_errors}"


def test_no_duplicate_tool_ids():
    """Every tool ID must be unique across all base registries."""
    errors = validate_app(_build_full_app())
    tool_errors = [e for e in errors if "Duplicate tool ID" in e]
    assert tool_errors == [], f"Duplicate tools in base config: {tool_errors}"


def test_no_duplicate_role_ids():
    """Every role ID must be unique in ALL_CONTRIB_ROLES."""
    ids = [r.id for r in ALL_CONTRIB_ROLES]
    assert len(ids) == len(set(ids)), f"Duplicate role IDs: {[x for x in ids if ids.count(x) > 1]}"


def test_base_config_validates_cleanly():
    """The full base config should pass validation with zero errors."""
    errors = validate_app(_build_full_app())
    assert errors == [], f"Base config validation errors: {errors}"


def test_generalist_role_has_contrib_workflows():
    """The generalist role should carry the built-in workflows so they
    appear in the chat input's workflow selector without any user-side
    registration.
    """
    generalist = next(r for r in ALL_CONTRIB_ROLES if r.id == "generalist")
    attached_ids = {wf.id for wf in generalist.workflows}
    expected_ids = {wf.id for wf in ALL_CONTRIB_WORKFLOWS}
    assert expected_ids.issubset(attached_ids), (
        f"Generalist role is missing contrib workflows: "
        f"{expected_ids - attached_ids}"
    )
