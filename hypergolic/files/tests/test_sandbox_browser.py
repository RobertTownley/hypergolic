from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.files import sandbox_browser
from hypergolic.sandbox.manager.types import ExecResult, SandboxError, SandboxNotReadyError
from hypergolic.sandbox.model.containers import Container, Volume
from hypergolic.sandbox.model.sandbox import ProjectSandbox
from tests.conftest import make_project, make_session

MOD = "hypergolic.files.sandbox_browser"


def _sandbox() -> ProjectSandbox:
    return ProjectSandbox(
        id="sb",
        containers=[
            Container(id="app", image="python:3.12"),
            Container(id="db", image="postgres:16", skip_workspace_mount=True),
        ],
        volumes=[
            Volume(id="pgdata", mounts={"db": "/var/lib/postgresql/data"}),
            Volume(id="cache", mounts={"app": "/cache"}),
        ],
    )


def _seed(tmp_path, *, pid="sb-proj", configure=True):
    proj = make_project(pid=pid, name="SBTest", path=str(tmp_path / "base"))
    if configure:
        proj.configure_sandbox(_sandbox())
    wt = tmp_path / "wt"
    wt.mkdir()
    return make_session(project_id=pid, worktree_path=str(wt))


def test_list_containers_derives_roots_from_compose_model(tmp_path):
    sid = _seed(tmp_path)
    resp = sandbox_browser.list_containers(sid, _sandbox())

    containers = {c.id: c for c in resp.containers}
    assert set(containers) == {"app", "db"}

    app_roots = {r.path: r for r in containers["app"].roots}
    assert app_roots["/app"].label == "Project worktree"
    assert "/shared" in app_roots
    assert app_roots["/cache"].label == "cache"

    db_roots = {r.path: r for r in containers["db"].roots}
    assert "/app" not in db_roots
    assert "/shared" not in db_roots
    assert db_roots["/var/lib/postgresql/data"].label == "pgdata"


def test_list_containers_default_root_is_workspace(tmp_path):
    sid = _seed(tmp_path)
    resp = sandbox_browser.list_containers(sid, _sandbox())
    app = next(c for c in resp.containers if c.id == "app")
    assert app.roots[0].path == "/app"


def test_list_containers_none_sandbox_returns_empty(tmp_path):
    sid = _seed(tmp_path, configure=False)
    resp = sandbox_browser.list_containers(sid, None)
    assert resp.containers == []


@pytest.mark.parametrize("bad", ["..", "../etc", "a/../../etc", "/abs"])
def test_normalize_rejects_traversal(bad):
    with pytest.raises(ValueError):
        sandbox_browser._normalize_within_root("/app", bad)


def test_normalize_joins_relative_path():
    assert sandbox_browser._normalize_within_root("/app", "src/x") == "/app/src/x"
    assert sandbox_browser._normalize_within_root("/app", None) == "/app"


async def _exec_returns(stdout="", stderr="", rc=0):
    return AsyncMock(return_value=ExecResult(stdout=stdout, stderr=stderr, returncode=rc))


async def test_list_directory_parses_ls_output(tmp_path):
    sid = _seed(tmp_path)
    fake = await _exec_returns(stdout="src/\nREADME.md\n.env\n")
    with patch(f"{MOD}.exec_in_sandbox", fake):
        resp = await sandbox_browser.list_directory(sid, "app", "/app", None, "/proj")

    names = [(n.name, n.is_dir) for n in resp.nodes]
    assert names[0] == ("src", True)
    assert ("README.md", False) in names
    assert ("src/", True) not in names


async def test_list_directory_propagates_sandbox_error(tmp_path):
    sid = _seed(tmp_path)
    fake = AsyncMock(side_effect=SandboxError("not running"))
    with patch(f"{MOD}.exec_in_sandbox", fake):
        with pytest.raises(SandboxError):
            await sandbox_browser.list_directory(sid, "app", "/app", None, "/proj")


async def test_read_file_returns_content(tmp_path):
    sid = _seed(tmp_path)
    fake = await _exec_returns(stdout="hello world\n")
    with patch(f"{MOD}.exec_in_sandbox", fake):
        resp = await sandbox_browser.read_file(sid, "app", "/app", "x.txt", "/proj")
    assert resp.content == "hello world\n"
    assert resp.truncated is False


async def test_read_file_rejects_binary(tmp_path):
    sid = _seed(tmp_path)
    fake = await _exec_returns(stdout="ab\x00cd")
    with patch(f"{MOD}.exec_in_sandbox", fake):
        with pytest.raises(ValueError):
            await sandbox_browser.read_file(sid, "app", "/app", "x.bin", "/proj")


async def test_read_file_rejects_directory(tmp_path):
    sid = _seed(tmp_path)
    fake = await _exec_returns(stderr="head: error reading: Is a directory", rc=3)
    with patch(f"{MOD}.exec_in_sandbox", fake):
        with pytest.raises(IsADirectoryError):
            await sandbox_browser.read_file(sid, "app", "/app", "src", "/proj")


ROUTER = "hypergolic.files.router"


def test_endpoint_containers_returns_model(api_client, tmp_path):
    sid = _seed(tmp_path, pid="ep-proj")
    r = api_client.get("/api/files/sandbox/containers", params={"session_id": sid})
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()["containers"]}
    assert ids == {"app", "db"}


def test_endpoint_tree_maps_sandbox_error_to_409(api_client, tmp_path):
    sid = _seed(tmp_path, pid="ep-proj2")
    with patch(
        f"{ROUTER}.sandbox_browser.list_directory",
        AsyncMock(side_effect=SandboxError("down")),
    ):
        r = api_client.get(
            "/api/files/sandbox/tree",
            params={"session_id": sid, "container": "app", "root": "/app"},
        )
    assert r.status_code == 409


def test_endpoint_tree_maps_not_ready_to_503(api_client, tmp_path):
    sid = _seed(tmp_path, pid="ep-starting")
    with patch(
        f"{ROUTER}.sandbox_browser.list_directory",
        AsyncMock(side_effect=SandboxNotReadyError("Sandbox is starting up.")),
    ):
        r = api_client.get(
            "/api/files/sandbox/tree",
            params={"session_id": sid, "container": "app", "root": "/app"},
        )
    assert r.status_code == 503
    assert "starting" in r.json()["detail"]


def test_endpoint_read_maps_not_ready_to_503(api_client, tmp_path):
    sid = _seed(tmp_path, pid="ep-starting2")
    with patch(
        f"{ROUTER}.sandbox_browser.read_file",
        AsyncMock(side_effect=SandboxNotReadyError("Sandbox is starting up.")),
    ):
        r = api_client.get(
            "/api/files/sandbox/read",
            params={"session_id": sid, "container": "app", "root": "/app", "path": "f.py"},
        )
    assert r.status_code == 503


def test_endpoint_tree_maps_value_error_to_400(api_client, tmp_path):
    sid = _seed(tmp_path, pid="ep-proj3")
    with patch(
        f"{ROUTER}.sandbox_browser.list_directory",
        AsyncMock(side_effect=ValueError("traversal")),
    ):
        r = api_client.get(
            "/api/files/sandbox/tree",
            params={"session_id": sid, "container": "app", "root": "/app", "path": ".."},
        )
    assert r.status_code == 400


def test_endpoint_read_maps_directory_to_400(api_client, tmp_path):
    sid = _seed(tmp_path, pid="ep-proj4")
    with patch(
        f"{ROUTER}.sandbox_browser.read_file",
        AsyncMock(side_effect=IsADirectoryError()),
    ):
        r = api_client.get(
            "/api/files/sandbox/read",
            params={"session_id": sid, "container": "app", "root": "/app", "path": "src"},
        )
    assert r.status_code == 400
