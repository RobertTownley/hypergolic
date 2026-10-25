from tests.conftest import make_artifact, make_project, make_session


def test_list_artifacts_empty(api_client):
    resp = api_client.get("/api/artifacts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_artifacts_returns_rows(api_client):
    make_project("p1", "P", "/tmp/p1")
    sid = make_session(project_id="p1", sid="s1")
    aid = make_artifact(sid, workflow_id="wf-1", state_id="st-1", outcome="done", artifact_id="a-1")

    resp = api_client.get("/api/artifacts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == aid
    assert data[0]["session_id"] == sid
    assert data[0]["workflow_id"] == "wf-1"
    assert data[0]["state_id"] == "st-1"
    assert data[0]["outcome"] == "done"
    assert data[0]["artifact_id"] == "a-1"


def test_list_artifacts_filter_by_session_id(api_client):
    make_project("p1", "P", "/tmp/p1")
    sid1 = make_session(project_id="p1", sid="s1")
    sid2 = make_session(project_id="p1", sid="s2")
    make_artifact(sid1, artifact_id="a-1")
    make_artifact(sid2, artifact_id="a-2")

    resp = api_client.get("/api/artifacts", params={"session_id": sid1})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["session_id"] == sid1


def test_list_artifacts_filter_by_workflow_id(api_client):
    make_project("p1", "P", "/tmp/p1")
    sid = make_session(project_id="p1", sid="s1")
    make_artifact(sid, workflow_id="wf-A", artifact_id="a-1")
    make_artifact(sid, workflow_id="wf-B", artifact_id="a-2")

    resp = api_client.get("/api/artifacts", params={"workflow_id": "wf-A"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["workflow_id"] == "wf-A"


def test_list_artifacts_filter_by_outcome(api_client):
    make_project("p1", "P", "/tmp/p1")
    sid = make_session(project_id="p1", sid="s1")
    make_artifact(sid, outcome="approved", artifact_id="a-1")
    make_artifact(sid, outcome="rejected", artifact_id="a-2")

    resp = api_client.get("/api/artifacts", params={"outcome": "approved"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["outcome"] == "approved"


def test_list_artifacts_pagination(api_client):
    make_project("p1", "P", "/tmp/p1")
    sid = make_session(project_id="p1", sid="s1")
    for i in range(5):
        make_artifact(sid, artifact_id=f"a-{i}")

    resp = api_client.get("/api/artifacts", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp2 = api_client.get("/api/artifacts", params={"limit": 2, "offset": 2})
    assert resp2.status_code == 200
    assert len(resp2.json()) == 2


def test_get_artifact_found(api_client):
    make_project("p1", "P", "/tmp/p1")
    sid = make_session(project_id="p1", sid="s1")
    aid = make_artifact(sid, workflow_id="wf-1", state_id="st-1", outcome="ok", artifact_id="a-1",
                        content={"x": 1})

    resp = api_client.get(f"/api/artifacts/{aid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == aid
    assert data["content"] == {"x": 1}


def test_get_artifact_not_found(api_client):
    resp = api_client.get("/api/artifacts/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Artifact not found"
