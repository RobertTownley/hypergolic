"""Tests for hypergolic.skills.resolver."""

from unittest.mock import patch

from hypergolic.skills.resolver import resolve_roles, resolve_session_skills
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.harness.primitives.bundles import Role, Workflow, WorkflowState
from tests._factories import build_session as _session, build_skill as _skill
from hypergolic.harness.primitives.tool import Tool


def _app(*, roles=(), skills=(), workflows=()) -> App:
    """Build an App with the given registrations and set it active."""
    app = App()
    for r in roles:
        app.register_role(r)
    for s in skills:
        app.register_skill(s)
    for w in workflows:
        app.register_workflow(w)
    set_app(app)
    return app


def _session_skill_ids(session, workflow=None) -> list[str]:
    with patch(
        "hypergolic.skills.resolver.get_session_workflow", return_value=workflow
    ):
        return [s["id"] for s in resolve_session_skills(session)]


def test_resolve_roles_empty():
    _app()
    assert resolve_roles() == []


def test_resolve_roles_returns_and_deduplicates():
    _app(roles=[
        Role(id="generalist", name="Generalist", prompt="test"),
        Role(id="worker", name="Worker", prompt="worker prompt"),
        Role(id="worker", name="Worker Again", prompt="worker prompt"),
    ])
    ids = [r["id"] for r in resolve_roles()]
    assert "generalist" in ids
    assert ids.count("worker") == 1


def test_resolve_roles_includes_tools_and_skills():
    async def _run(ctx): ...
    tool = Tool(id="my-tool", name="My Tool", description="d", run=_run)
    _app(roles=[
        Role(id="generalist", name="Generalist", prompt="test",
             tools=[tool], skills=[_skill("sk-1")])
    ])
    generalist = next(r for r in resolve_roles() if r["id"] == "generalist")
    assert "my-tool" in generalist["tools"]
    assert "sk-1" in generalist["skills"]


def test_resolve_roles_with_prompt_path_expanded():
    _app(roles=[Role(id="r1", name="R1", prompt_path="~/some/path.md")])
    r = next(r for r in resolve_roles() if r["id"] == "r1")
    assert "~" not in r["prompt_path"]


def test_resolve_session_skills_app_level(sample_app):
    sample_app.register_skill(_skill("app-sk"))
    assert "app-sk" in _session_skill_ids(_session())


def test_resolve_session_skills_project_level(sample_app):
    sample_app.get_project("p-1").skills.append(_skill("proj-sk"))
    assert "proj-sk" in _session_skill_ids(_session(project_id="p-1"))


def test_resolve_session_skills_unregistered_project(sample_app):
    # A session pointing at a project that is no longer registered (e.g. the
    # user removed/renamed it in main.py) must degrade gracefully, not raise.
    sample_app.register_skill(_skill("app-sk"))
    assert "app-sk" in _session_skill_ids(_session(project_id="gone"))


def test_resolve_session_skills_role_level(sample_app):
    sample_app.register_role(
        Role(id="my-role", name="My Role", prompt="test", skills=[_skill("role-sk")])
    )
    assert "role-sk" in _session_skill_ids(_session(role="my-role"))


def test_resolve_session_skills_workflow_level(sample_app):
    wf = Workflow(
        id="wf-1",
        name="WF",
        description="d",
        initial_state="st-1",
        states=[WorkflowState(id="st-1", name="S", prompt="p", skills=[_skill("state-sk")])],
        skills=[_skill("wf-sk")],
    )
    sample_app.register_workflow(wf)
    ids = _session_skill_ids(_session(), workflow=("wf-1", "st-1"))
    assert "wf-sk" in ids
    assert "state-sk" in ids


def test_resolve_session_skills_deduplicates(sample_app):
    sk = _skill("shared-sk")
    sample_app.register_skill(sk)
    sample_app.get_project("p-1").skills.append(sk)
    ids = _session_skill_ids(_session(project_id="p-1"))
    assert ids.count("shared-sk") == 1


def test_resolve_session_skills_no_role(sample_app):
    """An unknown role contributes no skills (role lookup is optional)."""
    assert isinstance(_session_skill_ids(_session(role="unknown-role")), list)


def test_resolve_session_skills_workflow_not_found_in_resolver(sample_app):
    """An active workflow missing from app config is skipped without crashing."""
    ids = _session_skill_ids(_session(), workflow=("nonexistent-wf", "st-1"))
    assert isinstance(ids, list)


