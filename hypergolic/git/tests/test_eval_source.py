import subprocess
from pathlib import Path

import pytest

import hypergolic.config.settings as config
from hypergolic.git import eval_source


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def internals(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "session_internals_dir", lambda sid: tmp_path / "s" / sid)


@pytest.fixture
def host(tmp_path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("1")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "one")
    _git(repo, "tag", "v1")
    (repo / "f.txt").write_text("2")
    _git(repo, "commit", "-qam", "two")
    _git(repo, "tag", "-a", "v2", "-m", "v2")
    _git(repo, "branch", "ABC-9-later")
    return repo


def _remote_refs(source: Path, tmp_path: Path) -> set[str]:
    out = _git(tmp_path, "ls-remote", str(source))
    return {line.split("\t")[1] for line in out.splitlines()}


async def test_source_shows_only_the_pinned_branch_and_its_tags(internals, host, tmp_path):
    pin = _git(host, "rev-parse", "main~1")
    source = eval_source.ensure_eval_source("S1", host / ".git")
    await eval_source.seed_eval_source("S1", host, "main", pin)

    assert _remote_refs(source, tmp_path) == {"HEAD", "refs/heads/main", "refs/tags/v1"}
    assert _git(source, "rev-parse", "main") == pin
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", "--shared", str(source), str(clone))
    assert _git(clone, "log", "--format=%s") == "one"


async def test_a_sim_land_adds_the_branch_to_the_source(internals, host, tmp_path):
    tip = _git(host, "rev-parse", "main")
    source = eval_source.ensure_eval_source("S1", host / ".git")
    await eval_source.seed_eval_source("S1", host, "main", _git(host, "rev-parse", "main~1"))
    await eval_source.set_eval_branch("S1", "ABC-1-x", tip)

    assert "refs/heads/ABC-1-x" in _remote_refs(source, tmp_path)
    assert "refs/heads/ABC-9-later" not in _remote_refs(source, tmp_path)


def test_ensure_is_idempotent_and_alternates_into_the_host(internals, host):
    path = eval_source.ensure_eval_source("S1", host / ".git")
    assert eval_source.ensure_eval_source("S1", host / ".git") == path
    alternates = (path / "objects" / "info" / "alternates").read_text()
    assert alternates == f"{host / '.git'}/objects\n"
