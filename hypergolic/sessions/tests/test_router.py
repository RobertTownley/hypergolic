from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.skills import activation_rows
from hypergolic.db.engine import get_db
from hypergolic.db.models import DBSessionWorkflow
from tests._factories import build_session
from tests.conftest import make_message, make_project, make_session
from hypergolic.harness.primitives.bundles import OutputSchema, Workflow, WorkflowState
from hypergolic.sessions.description.store import save_description
from hypergolic.sessions.schemas import ToolInfo
from hypergolic.git.container_git import SandboxRepoUnavailable
from hypergolic.sessions.routes import transcript as transcript_routes
from hypergolic.prompts.builder import PromptBlock


@pytest.fixture
def sid():
    make_project("p1", "P1", "/tmp/p1")
    return make_session(sid="s1", project_id="p1")


def _worktree_session(tmp_path, sid, pid):
    ws = tmp_path / "ws"
    ws.mkdir()
    make_project(pid, "P", str(tmp_path / "proj"))
    make_session(sid=sid, project_id=pid, worktree_path=str(ws), worktree_branch=f"main-{sid}")
    return ws


def _make_workflow(wf_id, name, state_id, state_name):
    return Workflow(
        id=wf_id,
        name=name,
        description="desc",
        prompt_path=None,
        initial_state=state_id,
        states=[
            WorkflowState(
                id=state_id,
                name=state_name,
                prompt_path=None,
                output_schemas=[
                    OutputSchema(outcome="done", next_state=None, schema={}),
                ],
            ),
        ],
    )


def _tool_info(tool_id: str = "test-tool"):
    return ToolInfo(
        id=tool_id, name="Test Tool", description="A tool",
        reason="role", requires_approval=False, token_estimate=10,
    )


@contextmanager
def _context_patches(skills):
    with (
        patch("hypergolic.sessions.routes.context.command_tool_infos", return_value=[_tool_info()]),
        patch("hypergolic.sessions.routes.context.resolve_session_skills", return_value=skills),
        patch("hypergolic.sessions.routes.context.get_enabled_servers", return_value=[]),
        patch("hypergolic.sessions.routes.context.build_prompt_blocks", new=AsyncMock(return_value=[
            PromptBlock(source="base", text="Hello " * 100),
        ])),
    ):
        yield


@pytest.mark.db
def test_list_sessions_counts_messages_and_filters_by_project(api_client):
    make_project("p1", "P1", "/tmp/p1")
    make_project("p2", "P2", "/tmp/p2")
    make_session(project_id="p1", sid="s1")
    make_session(project_id="p2", sid="s2")
    make_message("s1", role="user", text="hi")
    make_message("s1", role="assistant", text="hello")
    save_description("s1", "Fix the bug")

    by_id = {s["id"]: s for s in api_client.get("/api/sessions").json()}
    assert (by_id["s1"]["message_count"], by_id["s1"]["description"]) == (2, "Fix the bug")
    assert by_id["s1"]["project_name"] == "P1"
    assert (by_id["s2"]["message_count"], by_id["s2"]["description"]) == (0, None)
    assert [s["id"] for s in api_client.get("/api/sessions", params={"project_id": "p1"}).json()] == ["s1"]
    assert api_client.get("/api/sessions", params={"project_id": "p3"}).json() == []


@pytest.mark.db
def test_list_sessions_with_workflow(api_client):
    make_project("p1", "P1", "/tmp/p1")
    sid = make_session(project_id="p1", sid="s1")
    with get_db() as db:
        db.add(DBSessionWorkflow(
            session_id=sid,
            workflow_id="wf-test",
            current_state_id="state-a",
            deleted_at=None,
        ))

    mock_wf = _make_workflow("wf-test", "Test Workflow", "state-a", "Alpha State")
    with patch("hypergolic.sessions.routes.listing.get_workflow", return_value=mock_wf):
        resp = api_client.get("/api/sessions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    s = data[0]
    assert s["workflow_id"] == "wf-test"
    assert s["workflow_name"] == "Test Workflow"
    assert s["workflow_state_name"] == "Alpha State"


def test_create_session(api_client):
    make_project("proj-1", "TestProject", "/tmp/p")
    seed_project = "proj-1"

    def create(**kw):
        make_session(sid="s-new", project_id=kw["project_id"], base_branch=kw["base_branch"])
        return build_session("s-new", project_id=kw["project_id"])

    with (
        patch("hypergolic.sessions.routes.lifecycle.create_session", side_effect=create) as created,
        patch("hypergolic.sessions.routes.lifecycle.get_session_workflow", return_value=None),
    ):
        resp = api_client.post("/api/sessions", json={
            "project_id": seed_project,
            "model_tier": "Medium",
            "role": "generalist",
            "base_branch": "main",
        })
    created.assert_called_once_with(
        project_id="proj-1", base_branch="main", model_tier="Medium", role="generalist",
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == seed_project
    assert data["project_name"] == "TestProject"
    assert data["role"] == "generalist"
    assert data["model_tier"] == "Medium"
    assert data["message_count"] == 0
    assert data["base_branch"] == "main"


def test_conclude_preview_missing_worktree_directory(api_client, tmp_path):
    make_project("p-cp1", "P", str(tmp_path))
    sid = make_session(sid="s-cp1", project_id="p-cp1", worktree_path=str(tmp_path / "gone"))

    resp = api_client.get(f"/api/sessions/{sid}/conclude-preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_worktree_session"] is True
    assert data["unmerged_count"] == 0


@pytest.mark.parametrize("count", [0, 2])
def test_conclude_preview_reports_unmerged_commits(api_client, tmp_path, monkeypatch, count):
    ws = _worktree_session(tmp_path, "s-cp2", "p-cp2")
    seen = []

    def fake_count(repo, base, branch):
        seen.append((repo, base, branch))
        return count

    monkeypatch.setattr(transcript_routes, "unmerged_commit_count", fake_count)

    resp = api_client.get("/api/sessions/s-cp2/conclude-preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_worktree_session"] is True
    assert data["branch_has_unmerged_commits"] is (count > 0)
    assert data["unmerged_count"] == count
    assert seen == [(ws, "main", "main-s-cp2")]


def test_conclude_preview_stopped_sandbox(api_client, tmp_path, monkeypatch):
    ws = _worktree_session(tmp_path, "s-cp6", "p-cp6")

    def unavailable(*args, **kwargs):
        raise SandboxRepoUnavailable(ws)

    monkeypatch.setattr(transcript_routes, "unmerged_commit_count", unavailable)

    resp = api_client.get("/api/sessions/s-cp6/conclude-preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_worktree_session"] is True
    assert data["unmerged_count"] == 0


def test_list_roles(api_client):
    mock_roles = [
        {"id": "generalist", "name": "Generalist", "source": "harness"},
        {"id": "worker", "name": "Worker", "source": "harness"},
    ]
    with patch("hypergolic.sessions.routes.lifecycle.resolve_roles", return_value=mock_roles):
        resp = api_client.get("/api/sessions/roles")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "generalist"
    assert data[1]["name"] == "Worker"


def test_get_messages(api_client, sid):
    make_message(sid, role="user", text="first")
    make_message(sid, role="assistant", text="second")

    with patch("hypergolic.sessions.routes.transcript._build_tool_display_names", return_value={}):
        resp = api_client.get(f"/api/sessions/{sid}/messages")

    assert resp.status_code == 200
    msgs = resp.json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"][0] == {"type": "text", "text": "first"}


def test_get_messages_with_tool_display_names(api_client, sid):
    make_message(sid, role="user", text="hi")

    resp = api_client.get(f"/api/sessions/{sid}/messages")

    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_context(api_client, sid):
    with _context_patches([
        {"id": "sk1", "name": "Skill 1", "description": "d", "source": "harness"},
    ]):
        resp = api_client.get(f"/api/sessions/{sid}/context")

    assert resp.status_code == 200
    data = resp.json()
    assert data["tools_count"] == 1
    assert data["tools_token_estimate"] > 0
    assert data["tools"][0]["id"] == "test-tool"
    assert data["skills_summary"]["total"] == 1
    assert data["skills_summary"]["activated"] == []
    assert data["mcp_enabled"] == []
    assert data["prompt_token_estimate"] > 0


async def test_get_context_reports_activated_skills(api_client, sid):
    await activation_rows.record(sid, "git")
    with _context_patches([]):
        resp = api_client.get(f"/api/sessions/{sid}/context")
    assert resp.json()["skills_summary"]["activated"] == ["git"]


def test_get_prompt(api_client, sid):
    mock_blocks = [
        PromptBlock(source="Base prompt", text="You are helpful"),
        PromptBlock(source="Session context", text="Session info here"),
    ]
    with patch(
        "hypergolic.sessions.routes.context.build_prompt_blocks",
        new=AsyncMock(return_value=mock_blocks),
    ):
        resp = api_client.get(f"/api/sessions/{sid}/prompt")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["source"] == "Base prompt"
    assert data[0]["content"] == "You are helpful"
    assert data[0]["token_estimate"] == len("You are helpful") // 4


def test_get_session_workflows(api_client, sid):
    mock_wf = _make_workflow("wf-1", "Test Workflow", "s1", "Start")
    with patch("hypergolic.sessions.routes.context.resolve_workflows_for_session", return_value=[mock_wf]):
        resp = api_client.get(f"/api/sessions/{sid}/workflows")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "wf-1"
    assert data[0]["name"] == "Test Workflow"
    assert data[0]["initial_state"] == "s1"
    assert len(data[0]["states"]) == 1
    assert data[0]["states"][0]["id"] == "s1"


def test_get_session_skills(api_client, sid):
    mock_skills = [
        {"id": "sk1", "name": "Alpha", "description": "First", "source": "harness"},
        {"id": "sk2", "name": "Beta", "description": "Second", "source": "harness"},
    ]

    with patch("hypergolic.sessions.routes.context.resolve_session_skills", return_value=mock_skills):
        resp = api_client.get(f"/api/sessions/{sid}/skills")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {s["id"] for s in data} == {"sk1", "sk2"}
