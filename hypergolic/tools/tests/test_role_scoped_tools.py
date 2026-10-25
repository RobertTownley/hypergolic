"""Role-scoped capability.

Each role reaches only its declared commands plus app-level ones, and the
``dispatch`` command it builds targets exactly the roles it declares.
"""

import os

import pytest
from unittest.mock import patch

from hypergolic.contrib.roles.registry import (
    ALL_CONTRIB_ROLES,
    generalist_role,
    reviewer_role,
    researcher_role,
    worker_role,
)
from hypergolic.contrib.skills.registry import ALL_CONTRIB_SKILLS
from hypergolic.contrib.tools.registry import UNIVERSAL_TOOLS
from hypergolic.harness.app.core import App
from hypergolic.harness.primitives.bundles import Role
from hypergolic.harness.project import Project
from hypergolic.harness.app.state import set_app
from hypergolic.schemas import Session
from tests._factories import build_session, commands_for
from hypergolic.harness.app.validation import validate_app


def _make_app() -> App:
    app = App()
    app.register_tools(UNIVERSAL_TOOLS)
    app.register_roles(ALL_CONTRIB_ROLES)
    app.register_skills(ALL_CONTRIB_SKILLS)
    app.register_project(
        Project(id="p1", name="P1", description="d", git_root="/tmp/test")
    )
    set_app(app)
    return app


def _make_session(role: str = "generalist", **kwargs) -> Session:
    return build_session("s1", project_id="p1", project_path="/tmp/test", role=role, **kwargs)


def _ids(role: str = "generalist", **kwargs) -> set[str]:
    return set(commands_for(_make_session(role, **kwargs)))


def test_git_skill_is_generalist_scoped():
    """pull_request lives only in the git skill, which only the generalist
    carries — children structurally cannot integrate or publish."""
    assert "git" in {sk.id for sk in generalist_role.skills}
    assert not any(sk.id == "git" for sk in ALL_CONTRIB_SKILLS)
    for role in (worker_role, reviewer_role, researcher_role):
        assert "git" not in {sk.id for sk in role.skills}


# --- the session's command set ---


@pytest.mark.parametrize("expected", ["mcp", "history"])
def test_a_skills_command_needs_no_activation(expected):
    _make_app()
    assert expected in _ids("generalist")


def _dispatch_role_enum_values(commands) -> set[str]:
    dispatch = commands["dispatch"]
    schema = dispatch.input_schema.model_json_schema()
    role_schema = schema["properties"]["role"]
    if "anyOf" in role_schema:
        role_schema = next(o for o in role_schema["anyOf"] if o.get("type") != "null")
    if "$ref" in role_schema:
        def_name = role_schema["$ref"].rsplit("/", 1)[-1]
        role_schema = schema["$defs"][def_name]
    return set(role_schema["enum"])


def test_generalist_dispatch_role_enum_includes_generalist():
    _make_app()
    assert _dispatch_role_enum_values(commands_for(_make_session())) == {
        "generalist", "worker", "researcher",
    }


def test_dispatch_stops_at_the_nesting_limit():
    """Depth counts the top-level session: with the default limit 3 a child
    can dispatch, and a grandchild cannot."""
    _make_app()
    parents = {"child-1": build_session("child-1", project_id="p1", parent_id="top-1")}
    load = lambda sid: parents.get(sid) or build_session(sid, project_id="p1")  # noqa: E731
    with patch("hypergolic.sessions.operations.load_session", side_effect=load):
        assert "dispatch" in _ids("generalist", parent_id="top-1")
        assert "dispatch" not in _ids("generalist", parent_id="child-1")


def test_modify_role_extends_dispatch_targets():
    app = _make_app()
    app.register_role(Role(id="custom", name="Custom", prompt="p"))
    app.modify_role("generalist", add_dispatch_targets=["custom"])
    assert _dispatch_role_enum_values(commands_for(_make_session())) == {
        "generalist", "worker", "researcher", "custom",
    }

    app.modify_role("generalist", remove_dispatch_targets=["custom", "worker", "generalist"])
    assert _dispatch_role_enum_values(commands_for(_make_session())) == {"researcher"}


def test_validation_rejects_unknown_dispatch_target():
    app = _make_app()
    assert not any("dispatch target" in e for e in validate_app(app))
    app.modify_role("generalist", add_dispatch_targets=["ghost"])
    assert any("dispatch target \'ghost\'" in e for e in validate_app(app))


def test_reviewer_gets_its_role_command_and_no_integration_commands():
    _make_app()
    ids = _ids("reviewer")
    assert {"git", "host_cmd", "dispatch", "pull_request", "merge_child", "diff_child"}.isdisjoint(ids)


def test_researcher_gets_no_integration_commands():
    _make_app()
    ids = _ids("researcher")
    assert {"git", "host_cmd", "dispatch", "pull_request"}.isdisjoint(ids)


def test_worker_gets_review_but_no_integration():
    _make_app()
    ids = _ids("worker", parent_id="parent-1")
    assert {"review", "conclude"} <= ids
    assert {"dispatch", "pull_request", "merge_child", "diff_child", "host_cmd"}.isdisjoint(ids)


def test_generalist_reaches_the_git_skills_commands():
    _make_app()
    assert {"pull_request", "review"} <= _ids("generalist")


def test_every_role_reaches_land():
    """The quarantine hooks invoke `land` for whichever session pushed; it
    must resolve everywhere (children get a rejection with guidance, not a
    missing command)."""
    _make_app()
    for role in ("generalist", "reviewer", "researcher"):
        assert "land" in _ids(role), role
    assert "land" in _ids("worker", parent_id="parent-1")


def test_the_shell_is_never_a_command():
    """It is the one tool on the wire; a shim for it would recurse into the
    exec it came from."""
    _make_app()
    assert "cmd" not in _ids("researcher")


def test_unregistered_project_degrades():
    # A session pointing at a project not in the App (removed/renamed in
    # main.py) must still resolve its commands without raising.
    _make_app()
    session = build_session("s1", project_id="gone", role="researcher")
    assert "apropos" in set(commands_for(session))


def test_child_session_gets_conclude():
    _make_app()
    assert "conclude" in _ids("researcher", parent_id="parent-1")


def test_no_role_exposes_an_invocable_host_git_command():
    """Sandbox-owned repos: git is the image binary, never a host shim. The
    ``git`` id may still appear as the git *skill*'s advisory README — a docs
    entry, not an invocable command."""
    app = _make_app()
    app.register_role(Role(id="bare", name="Bare", prompt="p"))
    for role in ("bare", "generalist", "worker", "reviewer", "researcher"):
        session = build_session("s1", project_id="p1", role=role)
        commands = commands_for(session)
        entry = commands.get("git")
        assert entry is None or not entry.invocable, role


def test_unknown_role_still_yields_app_commands():
    """A session naming a role that no longer exists degrades to app-level
    capability rather than failing to build a prompt."""
    _make_app()
    commands = commands_for(_make_session("nonexistent"))
    assert commands
    assert not any(c.origin == "role" for c in commands.values())


# --- HYPERGOLIC_DISABLE_COMMANDS ---


@pytest.mark.parametrize("disabled", [True, False])
def test_disable_commands_gates_host_cmd(disabled):
    """host_cmd is present for the generalist unless HYPERGOLIC_DISABLE_COMMANDS is set."""
    _make_app()
    env = {k: v for k, v in os.environ.items() if k != "HYPERGOLIC_DISABLE_COMMANDS"}
    if disabled:
        env["HYPERGOLIC_DISABLE_COMMANDS"] = "1"
    with patch.dict("os.environ", env, clear=True):
        ids = _ids("generalist")
    assert ("host_cmd" in ids) is not disabled
