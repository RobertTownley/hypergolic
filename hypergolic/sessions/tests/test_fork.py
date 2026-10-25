import pytest

from hypergolic.messages import message_rows
from hypergolic.sessions.operations import clear_session_worktree_fields, fork_session
from tests.conftest import make_message, make_project, make_session

def _seed_conversation(sid: str) -> None:
    make_message(sid, "user", "first")
    make_message(sid, "assistant", "reply", model="m1", stop_reason="end_turn", usage={"input_tokens": 5})


def test_fork_copies_messages_into_new_session(seed_project):
    sid = make_session(project_id=seed_project, base_branch="main")
    _seed_conversation(sid)

    forked = fork_session(sid)

    assert forked.id != sid
    assert forked.project_id == seed_project
    assert forked.base_branch == "main"
    assert forked.role == "generalist"
    rows = message_rows.for_session(forked.id)
    assert [(r.role, r.sequence) for r in rows] == [("user", 1), ("assistant", 2)]
    assert rows[0].content == [{"type": "text", "text": "first"}]
    assert (rows[1].model, rows[1].usage) == ("m1", {"input_tokens": 5})
    assert rows[0].id != message_rows.for_session(sid)[0].id


def test_fork_with_workspace_roots_on_source_branch(seed_project):
    sid = make_session(
        project_id=seed_project, base_branch="main",
        worktree_branch="main-src1", worktree_path="/tmp/wt/main-src1",
    )
    _seed_conversation(sid)

    forked = fork_session(sid, with_workspace=True)

    assert forked.base_branch == "main-src1"
    assert forked.worktree_branch == f"main-src1-{forked.id}"
    assert len(message_rows.for_session(forked.id)) == 2


def test_fork_with_workspace_fails_after_branch_deleted():
    make_project("p1", "P1", "/tmp/p1")
    sid = make_session(project_id="p1", base_branch="main")
    clear_session_worktree_fields(sid, clear_branch=True)

    with pytest.raises(ValueError, match="merged or discarded"):
        fork_session(sid, with_workspace=True)


def test_fork_with_workspace_endpoint(api_client, seed_project):
    sid = make_session(
        project_id=seed_project, base_branch="main",
        worktree_branch="main-src1", worktree_path="/tmp/wt/main-src1",
    )
    _seed_conversation(sid)

    res = api_client.post(f"/api/sessions/{sid}/fork", json={"with_workspace": True})
    assert res.status_code == 200
    assert res.json()["base_branch"] == "main-src1"

    res = api_client.post(f"/api/sessions/{sid}/fork", json={"with_workspace": False})
    assert res.json()["base_branch"] == "main"


def test_fork_endpoint(api_client, seed_project):
    sid = make_session(project_id=seed_project, base_branch="main")
    _seed_conversation(sid)

    res = api_client.post(f"/api/sessions/{sid}/fork")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] != sid
    assert body["message_count"] == 2
    assert body["base_branch"] == "main"


def test_fork_endpoint_missing_session(api_client):
    res = api_client.post("/api/sessions/nope/fork")
    assert res.status_code == 404
