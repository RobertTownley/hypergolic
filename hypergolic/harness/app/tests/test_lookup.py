"""Tests for hypergolic.harness.app.lookup."""

import pytest

from hypergolic.harness.app.lookup import (
    _find_in_skill,
    collect_top_level_skills,
    find_skill,
)
from hypergolic.harness.app.core import App
from hypergolic.harness.primitives.bundles import Role, Skill, Workflow, WorkflowState
from hypergolic.harness.project import Project
from tests._factories import build_skill as _skill


def _wf(**kwargs) -> Workflow:
    return Workflow(
        id="wf1", name="WF", description="d", initial_state="s1",
        states=[WorkflowState(
            id="s1", name="S1", prompt="t", skills=kwargs.get("state_skills", []),
        )],
        skills=kwargs.get("wf_skills", []),
    )


def test_find_in_skill_traverses_nesting():
    grandchild = _skill("gc")
    parent = _skill("parent", children=[_skill("child", children=[grandchild])])
    assert _find_in_skill("parent", parent) is parent
    assert _find_in_skill("gc", parent) is grandchild
    assert _find_in_skill("missing", parent) is None


def _app_with_parent_in_app(parent: Skill) -> App:
    app = App()
    app.register_skill(parent)
    return app


def _app_with_parent_in_project(parent: Skill) -> App:
    app = App()
    app.register_project(Project(
        id="p1", name="P1", description="d", git_root="/tmp/p1", skills=[parent]))
    return app


def _app_with_parent_in_role(parent: Skill) -> App:
    app = App()
    app.register_role(Role(id="r1", name="R1", prompt="test", skills=[parent]))
    return app


def _app_with_parent_in_workflow(parent: Skill) -> App:
    app = App()
    app.register_workflow(_wf(wf_skills=[parent]))
    return app


def _app_with_parent_in_workflow_state(parent: Skill) -> App:
    app = App()
    app.register_workflow(_wf(state_skills=[parent]))
    return app


def _app_with_parent_in_project_workflow(parent: Skill) -> App:
    app = App()
    app.register_project(Project(
        id="p1", name="P1", description="d", git_root="/tmp/p1",
        workflows=[_wf(wf_skills=[parent])]))
    return app


def _app_with_parent_in_project_workflow_state(parent: Skill) -> App:
    app = App()
    app.register_project(Project(
        id="p1", name="P1", description="d", git_root="/tmp/p1",
        workflows=[_wf(state_skills=[parent])]))
    return app


ALL_SOURCES = [
    _app_with_parent_in_app,
    _app_with_parent_in_project,
    _app_with_parent_in_role,
    _app_with_parent_in_workflow,
    _app_with_parent_in_workflow_state,
    _app_with_parent_in_project_workflow,
    _app_with_parent_in_project_workflow_state,
]


@pytest.mark.parametrize("make_app", ALL_SOURCES)
def test_find_skill_resolves_nested_child_from_every_source(make_app):
    child = _skill("nested-child")
    parent = _skill("top", children=[child])
    app = make_app(parent)
    assert find_skill("top", app) is parent
    assert find_skill("nested-child", app) is child


def test_find_skill_not_found_returns_none():
    assert find_skill("missing", App()) is None


def test_collect_top_level_skills_all_sources():
    app = App()
    app.register_skill(_skill("app-skill"))
    app.register_project(Project(
        id="p1", name="P1", description="d", git_root="/tmp/p1",
        skills=[_skill("proj-skill")],
        workflows=[Workflow(
            id="pwf", name="PWF", description="d", initial_state="ps1",
            states=[WorkflowState(id="ps1", name="PS1", prompt="t",
                                  skills=[_skill("proj-state-skill")])],
            skills=[_skill("proj-wf-skill")],
        )],
    ))
    app.register_role(Role(id="r1", name="R1", prompt="t", skills=[_skill("role-skill")]))
    app.register_workflow(_wf(
        wf_skills=[_skill("wf-skill")], state_skills=[_skill("state-skill")]))

    result = collect_top_level_skills(app)
    assert {s.id for s in result} == {
        "app-skill", "proj-skill", "role-skill",
        "wf-skill", "state-skill", "proj-wf-skill", "proj-state-skill",
    }


def test_collect_top_level_skills_empty_app():
    assert collect_top_level_skills(App()) == []
