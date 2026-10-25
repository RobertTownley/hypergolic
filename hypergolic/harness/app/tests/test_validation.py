"""Tests for hypergolic.harness.app.validation."""

from pathlib import Path

import pytest

from hypergolic.harness.app.core import App
from hypergolic.harness.app.validation import (
    _collect_all_skills,
    _detect_skill_cycles,
    validate_app,
)
from hypergolic.harness.primitives.bundles import OutputSchema, Role, Workflow, WorkflowState
from hypergolic.harness.primitives.tool import Tool
from hypergolic.harness.project import Project
from tests._factories import build_skill as _skill


async def _noop(inp, ctx):
    return "ok"


def _tool(tid: str) -> Tool:
    return Tool(id=tid, name=tid, description="d", run=_noop)


def _app(*roles: Role) -> App:
    """App with a generalist role (validation's baseline requirement)."""
    app = App()
    app.register_role(Role(id="generalist", name="Generalist", prompt="test"))
    for role in roles:
        app.register_role(role)
    return app


def _git_root(path: Path) -> str:
    (path / ".git").mkdir(parents=True)
    return str(path)


def _project(git_root: str, pid: str = "p1", **kwargs) -> Project:
    return Project(id=pid, name=pid.upper(), description="d", git_root=git_root, **kwargs)


def _workflow(states: list[WorkflowState] | None = None, **kwargs) -> Workflow:
    return Workflow(
        id="wf1",
        name="WF",
        description="d",
        initial_state=kwargs.pop("initial_state", "s1"),
        states=states or [WorkflowState(id="s1", name="S1", prompt="t")],
        **kwargs,
    )


def test_collect_all_skills_flat():
    a, b = _skill("a"), _skill("b")
    assert [s.id for s in _collect_all_skills([a, b])] == ["a", "b"]


def test_collect_all_skills_nested():
    a = _skill("a", children=[_skill("b", children=[_skill("c")])])
    assert [s.id for s in _collect_all_skills([a])] == ["a", "b", "c"]


def test_collect_all_skills_empty():
    assert _collect_all_skills([]) == []


def test_detect_no_cycles_linear():
    a = _skill("a", children=[_skill("b")])
    b = _skill("b")
    assert _detect_skill_cycles([a, a.skills[0], b]) == []


def test_detect_direct_cycle():
    a = _skill("a", children=[_skill("b")])
    b = _skill("b", children=[_skill("a")])
    errors = _detect_skill_cycles([a, a.skills[0], b, b.skills[0]])
    assert any("Circular skill dependency" in e for e in errors)


def test_detect_indirect_cycle():
    a = _skill("a", children=[_skill("b")])
    b = _skill("b", children=[_skill("c")])
    c = _skill("c", children=[_skill("a")])
    errors = _detect_skill_cycles([a, a.skills[0], b, b.skills[0], c, c.skills[0]])
    assert any("Circular skill dependency" in e for e in errors)


def test_detect_cycles_empty():
    assert _detect_skill_cycles([]) == []


def test_detect_no_cycle_diamond():
    a = _skill("a", children=[_skill("b"), _skill("c")])
    b = _skill("b", children=[_skill("d")])
    c = _skill("c", children=[_skill("d")])
    all_skills = [a, a.skills[0], a.skills[1], b, b.skills[0], c, c.skills[0], _skill("d")]
    assert _detect_skill_cycles(all_skills) == []


def test_validate_no_roles_error():
    errors = validate_app(App())
    assert any("No roles registered" in e for e in errors)


def test_validate_missing_generalist_role():
    app = App()
    app.register_role(Role(id="other", name="Other", prompt="test"))
    errors = validate_app(app)
    assert any("generalist" in e for e in errors)


def test_validate_roles_ok():
    errors = validate_app(_app())
    assert not any("role" in e.lower() for e in errors)


def test_validate_duplicate_tool_ids_app_level():
    app = _app()
    app.register_tool(_tool("dup"))
    app.register_tool(_tool("dup"))
    errors = validate_app(app)
    assert any("Duplicate tool ID" in e and "dup" in e for e in errors)


def test_validate_tool_on_app_and_project_is_not_duplicate(tmp_path):
    # The same tool ID across different registration sources is intentional --
    # e.g. every project that configures a sandbox registers a "cmd" tool.
    app = _app()
    app.register_tool(_tool("shared"))
    proj = _project(_git_root(tmp_path))
    proj.register_tool(_tool("shared"))
    app.register_project(proj)
    errors = validate_app(app)
    assert not any("Duplicate tool ID" in e for e in errors)


def test_validate_cmd_tool_across_projects_is_not_duplicate(tmp_path):
    # Each configured project sandbox registers a tool hardcoded to id "cmd";
    # multiple sandboxed projects must coexist without a false duplicate error.
    app = _app()
    for pid in ("p1", "p2"):
        proj = _project(_git_root(tmp_path / pid), pid=pid)
        proj.register_tool(_tool("cmd"))
        app.register_project(proj)
    errors = validate_app(app)
    assert not any("Duplicate tool ID" in e for e in errors)


def test_validate_tool_ids_in_workflow():
    app = _app()
    app.register_workflow(_workflow(tools=[_tool("wf-tool"), _tool("wf-tool")]))
    errors = validate_app(app)
    assert any("Duplicate tool ID" in e and "wf-tool" in e for e in errors)


def test_validate_tool_ids_in_project_workflow(tmp_path):
    wf = _workflow(tools=[_tool("pt"), _tool("pt")])
    app = _app()
    app.register_project(_project(_git_root(tmp_path), workflows=[wf]))
    errors = validate_app(app)
    assert any("Duplicate tool ID" in e for e in errors)


def test_validate_duplicate_project_ids(tmp_path):
    git_root = _git_root(tmp_path)
    app = _app()
    app.register_projects(
        [_project(git_root, pid="same"), _project(git_root, pid="same")]
    )
    errors = validate_app(app)
    assert any("Duplicate project ID" in e and "same" in e for e in errors)


def test_validate_project_git_root_not_exist():
    app = _app()
    app.register_project(_project("/nonexistent/path/that/does/not/exist"))
    errors = validate_app(app)
    assert any("git_root does not exist" in e for e in errors)


def test_validate_project_git_root_not_a_repo(tmp_path):
    app = _app()
    app.register_project(_project(str(tmp_path)))
    errors = validate_app(app)
    assert any("not a git repo" in e for e in errors)


def test_validate_project_git_root_ok(tmp_path):
    app = _app()
    app.register_project(_project(_git_root(tmp_path)))
    errors = validate_app(app)
    assert not any("git_root" in e or "git repo" in e for e in errors)


def test_validate_project_prompt_path_not_found(tmp_path):
    app = _app()
    app.register_project(
        _project(_git_root(tmp_path), prompt_path=str(tmp_path / "nonexistent.md"))
    )
    errors = validate_app(app)
    assert any("prompt_path not found" in e for e in errors)


def test_validate_project_prompt_path_found(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("hello")
    app = _app()
    app.register_project(_project(_git_root(tmp_path), prompt_path=str(prompt_file)))
    errors = validate_app(app)
    assert not any("prompt_path" in e for e in errors)


def test_validate_workflow_initial_state_missing():
    app = _app()
    app.register_workflow(_workflow(initial_state="nonexistent"))
    errors = validate_app(app)
    assert any("initial_state" in e and "nonexistent" in e for e in errors)


@pytest.mark.parametrize("next_state,expect_error", [("ghost-state", True), (None, False)])
def test_validate_workflow_output_next_state(next_state, expect_error):
    app = _app()
    output = OutputSchema(
        outcome="done",
        schema={"type": "object", "properties": {}},
        next_state=next_state,
    )
    state = WorkflowState(id="s1", name="S1", prompt="t", output_schemas=[output])
    app.register_workflow(_workflow(states=[state]))
    errors = validate_app(app)
    assert any("ghost-state" in e for e in errors) == expect_error


def test_validate_duplicate_skill_ids_top_level():
    app = _app()
    app.register_skill(_skill("dup"))
    app.register_skill(_skill("dup"))
    errors = validate_app(app)
    assert any("Duplicate skill ID" in e and "dup" in e for e in errors)


def test_validate_duplicate_nested_skill_id_conflicts_with_top_level():
    app = _app()
    app.register_skill(_skill("parent", children=[_skill("same-id")]))
    app.register_skill(_skill("same-id"))
    errors = validate_app(app)
    assert any("Duplicate skill ID" in e and "same-id" in e for e in errors)


def test_validate_skill_on_app_and_role_is_not_duplicate():
    # Same skill ID across different registration sources is intentional.
    shared = _skill("shared")
    app = _app()
    role = app.get_role("generalist")
    assert role is not None
    role.skills.append(shared)
    app.register_skill(shared)
    errors = validate_app(app)
    assert not any("Duplicate skill ID" in e for e in errors)


def test_validate_skill_on_multiple_roles_is_not_duplicate():
    shared = _skill("shared")
    app = _app(Role(id="other", name="Other", prompt="p", skills=[shared]))
    role = app.get_role("generalist")
    assert role is not None
    role.skills.append(shared)
    errors = validate_app(app)
    assert not any("Duplicate skill ID" in e for e in errors)


def test_validate_different_instances_same_id_on_app_and_role_is_not_duplicate():
    # Distinct skill instances that share an ID (e.g. a user re-declaring a
    # built-in skill) represent the same skill and should not be flagged.
    app = _app()
    role = app.get_role("generalist")
    assert role is not None
    role.skills.append(_skill("shared"))
    app.register_skill(_skill("shared"))
    errors = validate_app(app)
    assert not any("Duplicate skill ID" in e for e in errors)


def test_validate_no_errors_clean_app(tmp_path):
    app = _app()
    app.register_project(_project(_git_root(tmp_path)))
    assert validate_app(app) == []
