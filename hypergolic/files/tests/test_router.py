from pathlib import Path
from unittest.mock import patch

import pytest

from hypergolic.files.language import detect_language
from hypergolic.files.schemas import FileNode, FileSearchMatch
from tests.conftest import make_project, make_session
from tests.helpers.git import seed_worktree_session
from watchfiles import Change
import asyncio

ROUTER = "hypergolic.files.router"


@pytest.fixture
def sess(tmp_path):
    sid, wt = seed_worktree_session(tmp_path)
    with patch(f"{ROUTER}.get_repo_root", return_value=str(wt)):
        yield sid, wt


def test_file_tree_returns_nested_nodes_with_session_id(api_client, sess):
    sid, wt = sess
    tree = [
        FileNode(name="src", path="src", is_dir=True, children=[
            FileNode(name="main.py", path="src/main.py", is_dir=False, git_status="M"),
        ]),
        FileNode(name="README.md", path="README.md", is_dir=False),
    ]
    with patch(f"{ROUTER}.build_file_tree", return_value=tree):
        resp = api_client.get("/api/files/tree", params={"session_id": sid})
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert data["root"] == str(wt)
    assert data["tree"][0]["children"][0]["git_status"] == "M"


def test_file_tree_requires_session_id(api_client):
    resp = api_client.get("/api/files/tree")
    assert resp.status_code == 422


def test_file_tree_unknown_session_returns_404(api_client):
    resp = api_client.get("/api/files/tree", params={"session_id": "no-such"})
    assert resp.status_code == 404
    assert "session" in resp.json()["detail"].lower()


def test_file_tree_falls_back_to_project_when_worktree_not_ready(api_client, tmp_path):
    project_path = tmp_path / "base"
    project_path.mkdir()
    make_project(pid="p1", path=str(project_path))
    sid = make_session(sid="s-1", project_id="p1")
    with (
        patch(f"{ROUTER}.get_repo_root", return_value=str(project_path)) as mock_root,
        patch(f"{ROUTER}.build_file_tree", return_value=[]) as mock_tree,
    ):
        resp = api_client.get("/api/files/tree", params={"session_id": sid})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == sid
    mock_root.assert_called_once_with(project_path)
    mock_tree.assert_called_once_with(project_path)


def test_raw_serves_file_with_media_type(api_client, sess):
    sid, wt = sess
    (wt / "page.html").write_text("<h1>hi</h1>")
    resp = api_client.get(f"/api/files/raw/{sid}/page.html")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.text == "<h1>hi</h1>"


@pytest.mark.parametrize(
    "path,status",
    [("%2e%2e/%2e%2e/etc/passwd", 403), ("nope.html", 404)],
    ids=["traversal-denied", "missing"],
)
def test_raw_error_paths(api_client, sess, path, status):
    sid, _ = sess
    resp = api_client.get(f"/api/files/raw/{sid}/{path}")
    assert resp.status_code == status


def test_raw_resolve_redirects_absolute_path(api_client, sess):
    sid, wt = sess
    sub = wt / "docs"
    sub.mkdir()
    (sub / "a b.html").write_text("x")
    resp = api_client.get(
        "/api/files/raw/resolve",
        params={"session_id": sid, "path": str(sub / "a b.html")},
        follow_redirects=False,
    )
    assert resp.status_code == 307
    assert resp.headers["location"] == f"/api/files/raw/{sid}/docs/a%20b.html"


def test_raw_resolve_relative_path_outside_repo_denied(api_client, sess):
    sid, _ = sess
    resp = api_client.get(
        "/api/files/raw/resolve",
        params={"session_id": sid, "path": "/etc/passwd"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_read_file_returns_content_and_language(api_client, sess):
    sid, wt = sess
    (wt / "hello.py").write_text("print('hello')\n")
    resp = api_client.get(
        "/api/files/read", params={"session_id": sid, "path": "hello.py"}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "session_id": sid,
        "path": "hello.py",
        "content": "print('hello')\n",
        "language": "python",
    }


@pytest.mark.parametrize(
    "path,status",
    [("nope.py", 404), ("../../../etc/passwd", 403)],
    ids=["missing", "traversal-denied"],
)
def test_read_file_error_paths(api_client, sess, path, status):
    sid, _ = sess
    resp = api_client.get("/api/files/read", params={"session_id": sid, "path": path})
    assert resp.status_code == status


def test_read_file_oserror_returns_500(api_client, sess):
    sid, wt = sess
    target = wt / "a.py"
    target.write_text("x")
    original_read = Path.read_text

    def _read(self, *args, **kwargs):
        if self == target.resolve():
            raise OSError("boom")
        return original_read(self, *args, **kwargs)

    with patch.object(Path, "read_text", _read):
        resp = api_client.get(
            "/api/files/read", params={"session_id": sid, "path": "a.py"}
        )
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("app.py", "python"),
        ("app.ts", "typescript"),
        ("style.css", "css"),
        ("config.yaml", "yaml"),
        ("Dockerfile", "docker"),
        ("Makefile", "makefile"),
        ("data.xml", "xml"),
        ("unknown.zzz", "text"),
    ],
)
def testdetect_language(filename, expected):
    assert detect_language(filename) == expected


def test_search_all_combines_names_and_contents(api_client, sess):
    sid, _ = sess
    name_matches = [FileSearchMatch(path="src/utils.py"), FileSearchMatch(path="src/helpers.py")]
    content_matches = [FileSearchMatch(path="src/main.py", line=10, text="import utils")]
    with (
        patch(f"{ROUTER}.search_file_names", return_value=name_matches),
        patch(f"{ROUTER}.search_file_contents", return_value=content_matches),
    ):
        resp = api_client.post(
            "/api/files/search",
            params={"session_id": sid},
            json={"query": "utils", "mode": "all"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert len(data["matches"]) == 3


def test_search_contents_only_skips_name_search(api_client, sess):
    sid, _ = sess
    with (
        patch(f"{ROUTER}.search_file_names") as mock_names,
        patch(f"{ROUTER}.search_file_contents", return_value=[]) as mock_contents,
    ):
        resp = api_client.post(
            "/api/files/search",
            params={"session_id": sid},
            json={"query": "x", "mode": "contents"},
        )
    assert resp.status_code == 200
    mock_names.assert_not_called()
    mock_contents.assert_called_once()


def test_search_all_passes_remaining_budget_to_contents(api_client, sess):
    sid, _ = sess
    name_matches = [FileSearchMatch(path=f"f{i}.py") for i in range(3)]
    with (
        patch(f"{ROUTER}.search_file_names", return_value=name_matches),
        patch(f"{ROUTER}.search_file_contents", return_value=[]) as mock_contents,
    ):
        api_client.post(
            "/api/files/search",
            params={"session_id": sid},
            json={"query": "x", "mode": "all", "max_results": 5},
        )
    assert mock_contents.call_args[0][4] == 2


def test_search_empty_query_short_circuits(api_client, sess):
    sid, _ = sess
    resp = api_client.post(
        "/api/files/search",
        params={"session_id": sid},
        json={"query": "  ", "mode": "files"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert data["matches"] == []


def _fake_awatch_factory(batches):
    async def _awatch(_root, *args, **kwargs):
        for b in batches:
            yield b

    return _awatch


@pytest.mark.timeout(5)
def test_watch_streams_connected_and_change_events(api_client, sess):
    sid, wt = sess
    batches = [{(Change.added, str(wt / "a.py")),
                (Change.modified, str(wt / "b.py")),
                (Change.deleted, str(wt / "c.py"))}]
    with patch(f"{ROUTER}.awatch", _fake_awatch_factory(batches)):
        with api_client.stream(
            "GET", "/api/files/watch", params={"session_id": sid},
        ) as resp:
            assert resp.status_code == 200
            body = b"".join(resp.iter_bytes())
    text = body.decode()
    assert '"type": "connected"' in text
    assert f'"session_id": "{sid}"' in text
    assert '"type": "changes"' in text
    assert '"change": "added"' in text
    assert '"change": "modified"' in text
    assert '"change": "deleted"' in text


@pytest.mark.timeout(5)
def test_watch_handles_cancellation(api_client, sess):
    sid, _ = sess

    class _CancellingAwatch:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise asyncio.CancelledError

    with patch(f"{ROUTER}.awatch", lambda _root, *a, **kw: _CancellingAwatch()):
        with api_client.stream(
            "GET", "/api/files/watch", params={"session_id": sid},
        ) as resp:
            assert resp.status_code == 200
            body = b"".join(resp.iter_bytes())
    assert '"type": "connected"' in body.decode()
