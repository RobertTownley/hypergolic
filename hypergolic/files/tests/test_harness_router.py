"""Tests for hypergolic.files.harness_router."""

from pathlib import Path
from unittest.mock import patch

from hypergolic.files.schemas import FileNode
from tests.conftest import make_project
import io
import zipfile

ROUTER = "hypergolic.files.harness_router"


def _seed_harness_project(tmp_path: Path) -> Path:
    root = tmp_path / "hypergolic"
    root.mkdir()
    make_project(pid="harness", name="My Harness", path=str(root))
    return root


# ── GET /api/harness/files/tree ─────────────────────────────────────────


def test_harness_tree_returns_tree_and_root(api_client, tmp_path):
    root = _seed_harness_project(tmp_path)
    tree = [
        FileNode(name="main.py", path="main.py", is_dir=False),
        FileNode(name="tools", path="tools", is_dir=True, children=[]),
    ]
    with (
        patch(f"{ROUTER}.get_repo_root", return_value=str(root)),
        patch(f"{ROUTER}.build_file_tree", return_value=tree),
    ):
        resp = api_client.get("/api/harness/files/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "harness"
    assert data["root"] == str(root)
    assert len(data["tree"]) == 2


def test_harness_tree_falls_back_to_home_config_when_project_missing(api_client, tmp_path):
    config = tmp_path / ".hypergolic"
    config.mkdir()
    (config / "main.py").write_text("app = App()\n")
    with patch(f"{ROUTER}.HARNESS_DIR", config):
        resp = api_client.get("/api/harness/files/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "harness"
    assert any(node["name"] == "main.py" for node in data["tree"])


def test_harness_tree_404_when_project_and_config_missing(api_client, tmp_path):
    with patch(f"{ROUTER}.HARNESS_DIR", tmp_path / "nohome" / ".hypergolic"):
        resp = api_client.get("/api/harness/files/tree")
    assert resp.status_code == 404
    assert "harness" in resp.json()["detail"].lower()


# ── GET /api/harness/files/read ─────────────────────────────────────────


def test_harness_read_returns_content_and_language(api_client, tmp_path):
    root = _seed_harness_project(tmp_path)
    (root / "main.py").write_text("app = App()\n")
    resp = api_client.get("/api/harness/files/read", params={"path": "main.py"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "harness"
    assert data["path"] == "main.py"
    assert data["content"] == "app = App()\n"
    assert data["language"] == "python"


def test_harness_read_path_traversal_denied(api_client, tmp_path):
    _seed_harness_project(tmp_path)
    resp = api_client.get(
        "/api/harness/files/read",
        params={"path": "../../../etc/passwd"},
    )
    assert resp.status_code == 403
    assert "denied" in resp.json()["detail"].lower()


def test_harness_read_missing_file_returns_404(api_client, tmp_path):
    _seed_harness_project(tmp_path)
    resp = api_client.get("/api/harness/files/read", params={"path": "missing.py"})
    assert resp.status_code == 404


def test_harness_read_falls_back_to_home_config_when_project_missing(api_client, tmp_path):
    config = tmp_path / ".hypergolic"
    config.mkdir()
    (config / "main.py").write_text("app = App()\n")
    with patch(f"{ROUTER}.HARNESS_DIR", config):
        resp = api_client.get("/api/harness/files/read", params={"path": "main.py"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "app = App()\n"


def test_harness_read_404_when_project_and_config_missing(api_client, tmp_path):
    with patch(f"{ROUTER}.HARNESS_DIR", tmp_path / "nohome" / ".hypergolic"):
        resp = api_client.get("/api/harness/files/read", params={"path": "main.py"})
    assert resp.status_code == 404
    assert "harness" in resp.json()["detail"].lower()


def test_harness_read_oserror_returns_500(api_client, tmp_path):
    root = _seed_harness_project(tmp_path)
    target = root / "main.py"
    target.write_text("x")
    original_read = Path.read_text

    def _raise(self, *args, **kwargs):
        if self == target.resolve():
            raise OSError("disk full")
        return original_read(self, *args, **kwargs)

    with patch.object(Path, "read_text", _raise):
        resp = api_client.get("/api/harness/files/read", params={"path": "main.py"})
    assert resp.status_code == 500
    assert "disk full" in resp.json()["detail"]


# ── GET /api/harness/files/export ───────────────────────────────────────


def test_harness_export_returns_zip_of_config(api_client, tmp_path):
    root = _seed_harness_project(tmp_path)
    (root / "main.py").write_text("app = App()\n")
    (root / ".gitignore").write_text("*.db\n*.log\neval_reports/\n.venv\n")
    (root / "prompts").mkdir()
    (root / "prompts" / "system.md").write_text("hello\n")

    resp = api_client.get("/api/harness/files/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]


    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = set(archive.namelist())
    assert "main.py" in names
    assert ".gitignore" in names
    assert "prompts/system.md" in names


def test_harness_export_excludes_gitignored_files(api_client, tmp_path):
    root = _seed_harness_project(tmp_path)
    (root / "main.py").write_text("app = App()\n")
    (root / ".gitignore").write_text("*.db\n*.log\neval_reports/\n")
    (root / "hypergolic.db").write_text("SQLITE")
    (root / "errors.log").write_text("boom")
    (root / "eval_reports").mkdir()
    (root / "eval_reports" / "run.md").write_text("report")

    resp = api_client.get("/api/harness/files/export")
    assert resp.status_code == 200


    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = set(archive.namelist())
    assert "main.py" in names
    assert "hypergolic.db" not in names
    assert "errors.log" not in names
    assert not any(n.startswith("eval_reports/") for n in names)
