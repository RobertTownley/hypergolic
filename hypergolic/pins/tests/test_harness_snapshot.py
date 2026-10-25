import subprocess
import sys
from pathlib import Path

import pytest

import types

from hypergolic.pins import harness_snapshot
from hypergolic.pins import runtime as rt
from hypergolic.harness.app.core import App


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture
def harness_repo(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "main.py").write_text(
        "from hypergolic.harness.app.core import App\n"
        "import extras\n"
        "app = App()\n"
        "app.use_defaults()\n"
        "app.marker = extras.MARKER\n"
    )
    (harness / "extras.py").write_text('MARKER = "v1"\n')
    _git(harness, "init", "-q", "-b", "main")
    _git(harness, "add", "-A")
    _git(harness, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "v1")
    monkeypatch.setattr(harness_snapshot.config, "HARNESS_DIR", harness)
    monkeypatch.setattr(harness_snapshot.config, "INTERNALS_DIR", tmp_path / "internals")
    monkeypatch.setattr(harness_snapshot, "_cache", {})
    return harness


@pytest.mark.timeout(10)
def test_snapshot_load_builds_app_at_sha_and_restores_modules(harness_repo):
    v1 = _git(harness_repo, "rev-parse", "HEAD")
    (harness_repo / "extras.py").write_text('MARKER = "v2"\n')
    _git(harness_repo, "add", "-A")
    _git(harness_repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "v2")

    path_before = list(sys.path)
    app = harness_snapshot.snapshot_harness_app(v1)
    assert isinstance(app, App)
    assert getattr(app, "marker") == "v1"
    assert "extras" not in sys.modules
    assert sys.path == path_before
    assert harness_snapshot.snapshot_harness_app(v1) is app


@pytest.mark.timeout(10)
def test_snapshot_load_shadows_live_harness_modules(harness_repo):
    v1 = _git(harness_repo, "rev-parse", "HEAD")
    live = types.ModuleType("extras")
    setattr(live, "MARKER", "live")
    live.__file__ = str(harness_repo / "extras.py")
    sys.modules["extras"] = live
    try:
        app = harness_snapshot.snapshot_harness_app(v1)
        assert getattr(app, "marker") == "v1"
        assert sys.modules["extras"] is live
    finally:
        sys.modules.pop("extras", None)


def test_release_deletes_unreferenced_checkouts(tmp_path, monkeypatch):
    monkeypatch.setattr(rt.config, "INTERNALS_DIR", tmp_path)
    monkeypatch.setattr(rt, "_snapshot_users", {})
    cache = {"a" * 40: object(), "b" * 40: object()}
    monkeypatch.setattr(rt, "_snapshot_evict_hooks", [lambda sha: cache.pop(sha, None)])
    root = tmp_path / "harness_snapshots"
    for sha in ("a" * 40, "b" * 40, "orphan"):
        (root / sha).mkdir(parents=True)

    rt.register_snapshot_use("s1", "a" * 40)
    rt.register_snapshot_use("s2", "a" * 40)
    rt.register_snapshot_use("s1", "b" * 40)

    rt.release_harness_snapshots("s1")
    assert (root / ("a" * 40)).is_dir()
    assert not (root / ("b" * 40)).exists() and not (root / "orphan").exists()
    assert "a" * 40 in cache and "b" * 40 not in cache

    rt.release_harness_snapshots("s2")
    assert not (root / ("a" * 40)).exists() and rt._snapshot_users == {}
