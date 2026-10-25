import pytest
from unittest.mock import patch

from hypergolic.files.schemas import FileSearchMatch
from hypergolic.sessions.schemas import SessionSearchMatch
from tests.conftest import make_project


@pytest.fixture(autouse=True)
def sessions_found():
    with patch("hypergolic.search.router.search_sessions", return_value=[]) as found:
        yield found


def _session_match(sid: str) -> SessionSearchMatch:
    return SessionSearchMatch(
        session_id=sid, project_id="proj-1", project_name="P", model_tier="Medium", created_at="",
        updated_at="", message_count=1, match_text="hit", match_role="user",
    )


def test_empty_query_returns_empty(api_client):
    resp = api_client.post("/api/search", json={"query": "   "})
    assert resp.status_code == 200
    assert resp.json()["matches"] == []


def test_mode_files_returns_file_matches(api_client):
    fake_matches = [FileSearchMatch(path="src/foo.py")]
    with patch("hypergolic.search.router.search_file_names", return_value=fake_matches), \
         patch("hypergolic.search.router.get_repo_root", return_value="/tmp"):
        resp = api_client.post("/api/search", json={"query": "foo", "mode": "files"})
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["type"] == "file"
    assert matches[0]["path"] == "src/foo.py"


def test_mode_contents_returns_content_matches(api_client):
    fake_matches = [FileSearchMatch(path="src/bar.py", line=10, text="hello world")]
    with patch("hypergolic.search.router.search_file_contents", return_value=fake_matches), \
         patch("hypergolic.search.router.get_repo_root", return_value="/tmp"):
        resp = api_client.post("/api/search", json={"query": "hello", "mode": "contents"})
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["line"] == 10
    assert matches[0]["text"] == "hello world"


def test_mode_sessions_returns_session_matches(api_client, sessions_found):
    sessions_found.return_value = [_session_match("s1")]
    resp = api_client.post("/api/search", json={"query": "searchterm", "mode": "sessions"})
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["type"] == "session"
    assert matches[0]["session_id"] == "s1"


def test_mode_all_combines_file_and_session_matches(api_client, sessions_found):
    sessions_found.return_value = [_session_match("s1")]
    file_match = FileSearchMatch(path="found.py")
    with patch("hypergolic.search.router.search_file_names", return_value=[file_match]), \
         patch("hypergolic.search.router.search_file_contents", return_value=[]), \
         patch("hypergolic.search.router.get_repo_root", return_value="/tmp"):
        resp = api_client.post("/api/search", json={"query": "combined", "mode": "all"})
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    types = {m["type"] for m in matches}
    assert "file" in types
    assert "session" in types


def test_mode_all_content_limit_respected(api_client):
    file_matches = [FileSearchMatch(path=f"f{i}.py") for i in range(3)]
    content_matches = [FileSearchMatch(path="c.py", line=1, text="x")]
    with patch("hypergolic.search.router.search_file_names", return_value=file_matches), \
         patch("hypergolic.search.router.search_file_contents", return_value=content_matches) as mock_contents, \
         patch("hypergolic.search.router.get_repo_root", return_value="/tmp"):
        resp = api_client.post("/api/search", json={"query": "x", "mode": "all", "max_file_results": 5})
    assert resp.status_code == 200
    call_args = mock_contents.call_args
    assert call_args[0][4] == 2


def test_mode_all_skips_contents_when_limit_zero(api_client):
    file_matches = [FileSearchMatch(path=f"f{i}.py") for i in range(3)]
    with patch("hypergolic.search.router.search_file_names", return_value=file_matches), \
         patch("hypergolic.search.router.search_file_contents") as mock_contents, \
         patch("hypergolic.search.router.get_repo_root", return_value="/tmp"):
        resp = api_client.post("/api/search", json={"query": "x", "mode": "all", "max_file_results": 3})
    assert resp.status_code == 200
    mock_contents.assert_not_called()


def test_project_not_found_returns_404(api_client):
    resp = api_client.post(
        "/api/search", json={"query": "foo", "mode": "files", "project_id": "nonexistent"}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


def test_project_id_resolves_path(api_client):
    make_project("p1", "MyProject", "/tmp/myproject")
    fake_matches = [FileSearchMatch(path="src/x.py")]
    with patch("hypergolic.search.router.search_file_names", return_value=fake_matches), \
         patch("hypergolic.search.router.get_repo_root", return_value="/tmp/myproject"):
        resp = api_client.post(
            "/api/search", json={"query": "x", "mode": "files", "project_id": "p1"}
        )
    assert resp.status_code == 200
    assert len(resp.json()["matches"]) == 1


def test_mode_sessions_skips_file_search(api_client):
    with patch("hypergolic.search.router.search_file_names") as mock_names, \
         patch("hypergolic.search.router.search_file_contents") as mock_contents:
        resp = api_client.post("/api/search", json={"query": "x", "mode": "sessions"})
    assert resp.status_code == 200
    mock_names.assert_not_called()
    mock_contents.assert_not_called()
