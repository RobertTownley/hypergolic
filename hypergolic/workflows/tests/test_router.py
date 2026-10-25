from unittest.mock import patch

from hypergolic.harness.primitives.bundles import OutputSchema, Workflow, WorkflowState


def _make_workflow(prompt_path: str | None = None, state_prompt_path: str | None = None) -> Workflow:
    return Workflow(
        id="wf-1",
        name="Test",
        description="",
        prompt_path=prompt_path,
        initial_state="s1",
        states=[
            WorkflowState(
                id="s1",
                name="Start",
                prompt_path=state_prompt_path,
                output_schemas=[OutputSchema(outcome="done", next_state=None, schema={})],
            )
        ],
    )


def test_get_prompt_content_not_in_whitelist(api_client):
    with patch("hypergolic.workflows.router.resolve_workflows", return_value=[_make_workflow("/allowed/prompt.md")]):
        resp = api_client.get("/api/workflows/prompt-content", params={"path": "/not/allowed.md"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_get_prompt_content_in_whitelist_missing_on_disk(api_client, tmp_path):
    prompt_path = str(tmp_path / "missing.md")
    with patch("hypergolic.workflows.router.resolve_workflows", return_value=[_make_workflow(prompt_path)]):
        resp = api_client.get("/api/workflows/prompt-content", params={"path": prompt_path})
    assert resp.status_code == 404
    assert "on disk" in resp.json()["detail"]


def test_get_prompt_content_happy_path(api_client, tmp_path):
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("You are a helpful assistant.")
    prompt_path = str(prompt_file)

    with patch("hypergolic.workflows.router.resolve_workflows", return_value=[_make_workflow(prompt_path)]):
        resp = api_client.get("/api/workflows/prompt-content", params={"path": prompt_path})

    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == prompt_path
    assert data["content"] == "You are a helpful assistant."


def test_get_prompt_content_state_level_path(api_client, tmp_path):
    """State-level prompt_path (not workflow-level) must also be whitelisted."""
    prompt_file = tmp_path / "state.md"
    prompt_file.write_text("State prompt.")
    prompt_path = str(prompt_file)

    with patch("hypergolic.workflows.router.resolve_workflows",
               return_value=[_make_workflow(state_prompt_path=prompt_path)]):
        resp = api_client.get("/api/workflows/prompt-content", params={"path": prompt_path})

    assert resp.status_code == 200
    assert resp.json()["content"] == "State prompt."
