import atexit
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_env_file = Path(__file__).parent / ".env.testing"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _value = _line.partition("=")
            os.environ[_key.strip()] = _value.strip()

os.environ["PATH"] = os.pathsep.join(
    entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry != "/tools/bin"
)
for _var in (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY", "GIT_PREFIX",
):
    os.environ.pop(_var, None)
for _var in (
    "HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE", "HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE_COMMANDS",
    "AWS_BEARER_TOKEN_BEDROCK",
):
    os.environ.pop(_var, None)

_test_home = Path(tempfile.mkdtemp(prefix="hypergolic-test-home-"))
atexit.register(shutil.rmtree, _test_home, ignore_errors=True)
(_test_home / ".gitconfig").write_text("[user]\n\tname = Test\n\temail = test@example.com\n[init]\n\tdefaultBranch = main\n")
os.environ.setdefault("DOCKER_CONFIG", str(Path.home() / ".docker"))
os.environ["HOME"] = str(_test_home)

_docker_spawns: list[str] = []
_popen_init = subprocess.Popen.__init__


def _forbid_docker_popen(self, args, *rest, **kwargs):
    argv = [args] if isinstance(args, (str, bytes, os.PathLike)) else list(args)
    program = os.fsdecode(argv[0]).split(maxsplit=1) if argv else []
    if program and Path(program[0]).name == "docker" and "PYTEST_CURRENT_TEST" in os.environ:
        _docker_spawns.append(" ".join(os.fsdecode(a) for a in argv))
        raise PermissionError("tests must not spawn docker")
    _popen_init(self, args, *rest, **kwargs)


subprocess.Popen.__init__ = _forbid_docker_popen

from tests.helpers.pg import ensure_test_database  # noqa: E402
ensure_test_database()

from collections.abc import Iterator  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from hypergolic.api import app  # noqa: E402
from hypergolic.config.settings import settings  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from hypergolic.db.engine import get_engine  # noqa: E402
from hypergolic.db.models import Base  # noqa: E402
from hypergolic.harness.app.core import App  # noqa: E402
from hypergolic.harness.app.state import set_app  # noqa: E402
import threading  # noqa: E402
from tests._factories import build_app  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402
from hypergolic.git import worktree_lifecycle  # noqa: E402
from tests.conftest import make_project  # noqa: E402
from tests.helpers.git import init_repo  # noqa: E402
from tests.helpers.tables import (  # noqa: E402
    FakeArtifactRows, FakeAuditRows, FakeMessageRows, FakeSessionRows, FakeWorkflowRows, MemoryTables,
)
import traceback  # noqa: E402


_schema_created = False
_db_touched = True
_db_opened_by: list[str] = []


@event.listens_for(Engine, "checkout")
def _mark_db_touched(*_):
    global _db_touched
    _db_touched = True
    root = str(Path(__file__).parent)
    frames = [f for f in traceback.extract_stack()[:-1] if f.filename.startswith(root) and "/.venv/" not in f.filename]
    _db_opened_by.append(" <- ".join(
        f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames[-5:])
    ))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("db") and not item.get_closest_marker("timeout"):
            item.add_marker(pytest.mark.timeout(2))


@pytest.fixture(autouse=True)
def _clean_db(request):
    if "/hg_test_" not in settings.HYPERGOLIC_DATABASE_URL:
        raise RuntimeError(
            f"Tests must use a scratch hg_test_* database, got: "
            f"{settings.HYPERGOLIC_DATABASE_URL}."
        )
    global _schema_created, _db_touched
    db_test = request.node.get_closest_marker("db") is not None
    if db_test and _db_touched:
        engine = get_engine()
        if not _schema_created:
            Base.metadata.create_all(engine)
            _schema_created = True
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
        _db_touched = False
    _db_opened_by.clear()
    _docker_spawns.clear()
    yield
    if _docker_spawns:
        pytest.fail(
            "spawned docker; patch the call site (e.g. patch_docker()):\n  " + "\n  ".join(_docker_spawns),
            pytrace=False,
        )
    if not db_test and _db_opened_by:
        sites = "\n  ".join(dict.fromkeys(_db_opened_by))
        pytest.fail(
            "opened a DB connection without @pytest.mark.db; seed the in-memory "
            f"tables (session_rows, message_rows, ...) or patch the query:\n  {sites}",
            pytrace=False,
        )
    for thread in list(threading.enumerate()):
        if thread.name.startswith(("worktree-create-", "worktree-teardown-")):
            thread.join(timeout=5.0)


@pytest.fixture(scope="session", autouse=True)
def _forbid_real_sandbox_dir(tmp_path_factory):
    parent = tmp_path_factory.mktemp("forbidden")
    parent.chmod(0o500)
    with patch(
        "hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR",
        parent / "sandboxes",
    ):
        yield


@pytest.fixture(autouse=True)
def _fresh_app():
    set_app(App())
    yield
    set_app(App())


@pytest.fixture
def sample_app():
    return build_app()


@pytest.fixture
def broadcast():
    return AsyncMock()


@pytest.fixture(autouse=True)
def _no_background_sandbox_work(monkeypatch):
    monkeypatch.setattr(
        "hypergolic.sessions.operations.schedule_reap", lambda *a, **k: None
    )


@pytest.fixture
def seed_project(tmp_path_factory, monkeypatch):
    project_dir = tmp_path_factory.mktemp("seed_project")
    wt_root = tmp_path_factory.mktemp("seed_project_worktrees")
    monkeypatch.setattr(settings, "HYPERGOLIC_WORKTREES_ROOT", str(wt_root))

    def noop_schedule(*, session_id, **_):
        worktree_lifecycle._get_or_create_event(session_id)
        worktree_lifecycle.set_worktree_status(session_id, "ready")
        worktree_lifecycle._signal_ready(session_id)
        thread = threading.Thread(target=lambda: None)
        thread.start()
        thread.join()
        return thread

    monkeypatch.setattr(
        "hypergolic.sessions.operations.schedule_create_and_seed",
        noop_schedule,
    )


    make_project("proj-1", "TestProject", str(project_dir))
    return "proj-1"


@pytest.fixture(autouse=True)
def _memory_tables(request, monkeypatch) -> MemoryTables | None:
    if request.node.get_closest_marker("db"):
        return None
    tables = MemoryTables()
    tables.install(monkeypatch)
    return tables


@pytest.fixture
def session_rows(_memory_tables: MemoryTables) -> FakeSessionRows:
    return _memory_tables.sessions


@pytest.fixture
def message_rows(_memory_tables: MemoryTables) -> FakeMessageRows:
    return _memory_tables.messages


@pytest.fixture
def workflow_rows(_memory_tables: MemoryTables) -> FakeWorkflowRows:
    return _memory_tables.workflows


@pytest.fixture
def artifact_rows(_memory_tables: MemoryTables) -> FakeArtifactRows:
    return _memory_tables.artifacts


@pytest.fixture
def audit_rows(_memory_tables: MemoryTables) -> FakeAuditRows:
    return _memory_tables.audit


@pytest.fixture(autouse=True)
def _no_host_harness_repo():
    with patch("hypergolic.api.ensure_harness_repo"):
        yield


@contextmanager
def _client_without_startup() -> Iterator[TestClient]:
    with (
        patch("hypergolic.api._startup_steps", AsyncMock()),
        patch("hypergolic.api.run_startup_maintenance", AsyncMock()),
        TestClient(app) as client,
    ):
        yield client


@pytest.fixture
def api_client():
    with patch("hypergolic.api.verify_token", return_value=True), _client_without_startup() as client:
        client.cookies.set("h_token", "test-token")
        yield client


@pytest.fixture
def unauth_client():
    with _client_without_startup() as client:
        yield client


@pytest.fixture
def sandbox_git_env(repo, tmp_path, monkeypatch):
    import shlex
    import subprocess

    from hypergolic.git import quarantine
    from hypergolic.git.commands import run_git_command
    from hypergolic.git.sandbox_integrate import SandboxGitError
    from hypergolic.git.sandbox_repo import hypergolic_ref

    monkeypatch.setattr(quarantine, "INTERNALS_DIR", tmp_path / "internals")

    async def fake_exec(session, project, script):
        assert session.worktree_path
        rewritten = script.replace("cd /app", f"cd {shlex.quote(session.worktree_path)}")
        result = subprocess.run(["bash", "-c", rewritten], capture_output=True, text=True)
        if result.returncode != 0:
            raise SandboxGitError(result.stderr.strip() or result.stdout.strip())
        return result.stdout

    async def fake_refresh(session, project, slot):
        assert session.worktree_path
        ref = hypergolic_ref(slot.ref_scope, slot.session_branch)
        result = run_git_command(
            "fetch", "--quiet", session.worktree_path,
            f"+refs/heads/{slot.session_branch}:{ref}",
            cwd=slot.host_repo,
        )
        if result.returncode != 0:
            raise SandboxGitError(result.stderr.strip())
        return ref

    monkeypatch.setattr("hypergolic.git.sandbox_integrate.exec_repo_git", fake_exec)
    monkeypatch.setattr("hypergolic.git.sandbox_integrate.refresh_slot_ref", fake_refresh)


@pytest.fixture
def repo(tmp_path):
    project = tmp_path / "project"
    init_repo(project)
    return project


@pytest.fixture
def worktrees_home(tmp_path, monkeypatch):
    root = tmp_path / "worktrees"
    monkeypatch.setenv("HYPERGOLIC_WORKTREES_ROOT", str(root))
    monkeypatch.setattr(settings, "HYPERGOLIC_WORKTREES_ROOT", str(root))
    return root
