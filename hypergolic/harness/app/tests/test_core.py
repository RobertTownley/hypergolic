"""Tests for hypergolic.harness.app.core."""

from unittest.mock import patch

import pytest

from hypergolic.enums import ModelTier
from hypergolic.harness.app.core import App
from hypergolic.harness.primitives.bundles import Role
from hypergolic.harness.primitives.tool import Tool
from hypergolic.harness.project import Project
from tests._factories import build_skill, build_workflow


async def _noop(inp, ctx):
    return "ok"


def _tool(tid: str = "t1") -> Tool:
    return Tool(id=tid, name=tid, description="d", run=_noop)


def _role(rid: str = "r1") -> Role:
    return Role(id=rid, name=rid, prompt="test")


def _project(pid: str = "p1") -> Project:
    return Project(id=pid, name=pid, description="d", git_root="/tmp/p1")


def test_app_default_construction():
    app = App()
    assert app.truncate_token_threshold == 50_000
    assert app.default_model_tier == ModelTier.MEDIUM
    assert app.projects == []
    assert app.tools == []
    assert app.roles == []
    assert app.skills == []
    assert app.workflows == []
    assert app._mcp_servers == {}


def test_app_custom_construction():
    app = App(truncate_token_threshold=100_000, default_model_tier=ModelTier.MEDIUM)
    assert app.truncate_token_threshold == 100_000


# Entity types whose getter returns ``None`` for a missing id. ``get_role`` /
# ``get_skill`` share the same register-then-lookup contract. (``get_project``
# is stricter — it raises on an unknown id — and is covered separately below.)
_GETTER_CASES = [
    pytest.param("roles", "register_role", "register_roles",
                 "get_role", _role, id="role"),
    pytest.param("skills", "register_skill", "register_skills",
                 "get_skill", build_skill, id="skill"),
]


@pytest.mark.parametrize("attr, reg_one, reg_many, getter, factory", _GETTER_CASES)
def test_register_and_get_entity(attr, reg_one, reg_many, getter, factory):
    app = App()
    one = factory("a")
    getattr(app, reg_one)(one)
    assert getattr(app, attr) == [one]
    assert getattr(app, getter)("a") == one
    assert getattr(app, getter)("nonexistent") is None

    getattr(app, reg_many)([factory("b"), factory("c")])
    assert len(getattr(app, attr)) == 3


def test_modify_role_leaves_registered_source_untouched():
    source = _role("a")
    app = App()
    app.register_role(source)
    app.modify_role("a", add_dispatch_targets=["worker"])
    assert source.dispatch_targets == []
    assert app.roles[0].dispatch_targets == ["worker"]


def test_get_project_raises_on_unknown_id():
    """A session always references a registered project, so ``get_project``
    raises (rather than returning ``None``) for an unknown id, surfacing a real
    harness bug. ``find_project`` is the soft variant for existence checks."""
    app = App()
    project = _project("a")
    app.register_project(project)

    assert app.get_project("a") is project
    assert app.find_project("a") is project
    assert app.find_project("nonexistent") is None
    with pytest.raises(KeyError):
        app.get_project("nonexistent")

    app.register_projects([_project("b"), _project("c")])
    assert len(app.projects) == 3


# Tools and workflows have no getter; only register-one / register-many.
@pytest.mark.parametrize("attr, reg_one, reg_many, factory", [
    pytest.param("tools", "register_tool", "register_tools", _tool, id="tool"),
    pytest.param("workflows", "register_workflow", "register_workflows",
                 build_workflow, id="workflow"),
])
def test_register_entity_without_getter(attr, reg_one, reg_many, factory):
    app = App()
    getattr(app, reg_one)(factory("a"))
    assert getattr(app, attr)[0].id == "a"
    getattr(app, reg_many)([factory("b"), factory("c")])
    assert len(getattr(app, attr)) == 3


def test_register_mcp_server():
    app = App()
    app.register_mcp_server("my-mcp", url="http://localhost:8080", token="abc")
    assert "my-mcp" in app._mcp_servers
    assert app._mcp_servers["my-mcp"]["url"] == "http://localhost:8080"


def test_validate_delegates_to_validate_app():
    with patch("hypergolic.harness.app.core.validate_app", return_value=[]) as mock:
        app = App()
        result = app._validate()
    mock.assert_called_once_with(app)
    assert result == []


def test_expand_paths_delegates():
    with patch("hypergolic.harness.app.core.expand_paths") as mock:
        app = App()
        app._expand_paths()
    mock.assert_called_once_with(app)


def test_call_delegates_to_run_app():
    with patch("hypergolic.harness.app.core.run_app") as mock:
        app = App()
        app()
    mock.assert_called_once_with(app)
