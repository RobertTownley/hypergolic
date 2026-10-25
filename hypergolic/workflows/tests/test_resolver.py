from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.harness.primitives.bundles import Role, Workflow
from hypergolic.harness.project import Project
from hypergolic.workflows.resolver import (
    get_workflow,
    resolve_workflows,
    resolve_workflows_for_session,
)
from tests._factories import build_session, build_workflow


def _make_workflow(wid: str = "wf-1") -> Workflow:
    return build_workflow(wid, state_id="s1")


def _make_app(*wf_ids: str) -> App:
    app = App()
    for wid in wf_ids:
        app.register_workflow(_make_workflow(wid))
    set_app(app)
    return app


def _project(pid: str = "p1", *wf_ids: str) -> Project:
    return Project(
        id=pid, name="P", description="d", git_root=f"/tmp/{pid}",
        workflows=[_make_workflow(wid) for wid in wf_ids],
    )


def _role(rid: str, *wf_ids: str) -> Role:
    return Role(
        id=rid, name=rid.title(), prompt="p",
        workflows=[_make_workflow(wid) for wid in wf_ids],
    )


def test_resolve_workflows_empty():
    _make_app()
    assert resolve_workflows() == []


def test_resolve_workflows_app_level():
    _make_app("wf-1", "wf-2")

    ids = [w.id for w in resolve_workflows()]
    assert "wf-1" in ids
    assert "wf-2" in ids


def test_resolve_workflows_project_level():
    _make_app().register_project(_project("p1", "proj-wf"))

    assert "proj-wf" in [w.id for w in resolve_workflows()]


def test_resolve_workflows_deduplicates():
    _make_app("shared-wf").register_project(_project("p1", "shared-wf"))

    ids = [w.id for w in resolve_workflows()]
    assert ids.count("shared-wf") == 1


def test_get_workflow_found_and_not_found():
    _make_app("target-wf")

    result = get_workflow("target-wf")
    assert result is not None
    assert result.id == "target-wf"

    assert get_workflow("nonexistent") is None


def test_get_workflow_from_project():
    _make_app().register_project(_project("p1", "proj-only-wf"))

    result = get_workflow("proj-only-wf")
    assert result is not None
    assert result.id == "proj-only-wf"


def test_resolve_workflows_includes_role_workflows():
    _make_app().register_role(_role("generalist", "role-wf"))

    assert "role-wf" in [w.id for w in resolve_workflows()]


def test_resolve_workflows_for_session_scopes_to_role():
    app = _make_app()
    app.register_role(_role("generalist", "generalist-wf"))
    app.register_role(_role("reviewer", "reviewer-wf"))
    app.register_project(_project("p-1"))

    generalist_ids = [w.id for w in resolve_workflows_for_session(build_session(role="generalist"))]
    reviewer_ids = [w.id for w in resolve_workflows_for_session(build_session(role="reviewer"))]

    assert "generalist-wf" in generalist_ids
    assert "reviewer-wf" not in generalist_ids
    assert "reviewer-wf" in reviewer_ids
    assert "generalist-wf" not in reviewer_ids


def test_resolve_workflows_for_session_unions_scopes():
    app = _make_app("app-wf")
    app.register_project(_project("p1", "proj-wf"))
    app.register_role(_role("generalist", "role-wf"))

    ids = [w.id for w in resolve_workflows_for_session(build_session(project_id="p1"))]
    assert {"app-wf", "proj-wf", "role-wf"}.issubset(set(ids))


def test_resolve_workflows_for_session_unregistered_project():
    _make_app("app-wf")

    ids = [w.id for w in resolve_workflows_for_session(build_session(project_id="gone"))]
    assert "app-wf" in ids


def test_resolve_workflows_for_session_deduplicates():
    app = _make_app()
    shared = _make_workflow("shared-wf")
    app.register_workflow(shared)
    app.register_role(Role(id="generalist", name="Generalist", prompt="p", workflows=[shared]))
    app.register_project(_project("p-1"))

    ids = [w.id for w in resolve_workflows_for_session(build_session())]
    assert ids.count("shared-wf") == 1


def test_get_workflow_finds_role_workflow():
    _make_app().register_role(_role("generalist", "only-on-role"))

    result = get_workflow("only-on-role")
    assert result is not None
    assert result.id == "only-on-role"
