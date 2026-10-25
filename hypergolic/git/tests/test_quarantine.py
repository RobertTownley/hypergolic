import subprocess
from pathlib import Path

import pytest

from hypergolic.commands.argv import parser_for
from hypergolic.contrib.tools.land import LandInput, LandTool
from hypergolic.git import quarantine


@pytest.fixture
def internals(tmp_path, monkeypatch):
    monkeypatch.setattr(quarantine, "INTERNALS_DIR", tmp_path)
    return tmp_path


def _host_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=repo, check=True,
    )
    return repo


def test_ensure_quarantine_is_idempotent_and_thin(internals, tmp_path):
    host = _host_repo(tmp_path)
    path = quarantine.ensure_quarantine(
        session_id="S1", repo="app", host_gitdir=host / ".git",
    )
    again = quarantine.ensure_quarantine(
        session_id="S1", repo="app", host_gitdir=host / ".git",
    )
    assert path == again == quarantine.quarantine_path("S1", "app")
    alternates = (path / "objects" / "info" / "alternates").read_text()
    assert alternates == f"{host / '.git'}/objects\n"
    update = (path / "hooks" / "update").read_text()
    assert 'refs/heads/*' in update and "--repo app" in update
    assert (path / "hooks" / "update").stat().st_mode & 0o111
    post = (path / "hooks" / "post-receive").read_text()
    assert "update-ref -d" in post
    config = (path / "config").read_text()
    assert "allowanysha1inwant = true" in config.lower()


def test_hooks_land_any_branch_and_pass_checkpoints(internals, tmp_path):
    hooks = quarantine.hook_sources("app")
    assert 'case "$1" in refs/heads/*)' in hooks["update"]
    assert '--branch "${1#refs/heads/}"' in hooks["update"]
    assert "GIT_PUSH_OPTION_COUNT" in hooks["update"]
    assert 'case "$ref" in refs/heads/*)' in hooks["post-receive"]
    assert quarantine.checkpoint_ref("s1") == "refs/hypergolic/checkpoint/s1"


@pytest.mark.timeout(10)
def test_land_push_flows_through_update_hook(internals, tmp_path):
    host = _host_repo(tmp_path)
    q = quarantine.ensure_quarantine(
        session_id="S3", repo="app", host_gitdir=host / ".git",
    )
    stub = tmp_path / "land-stub.sh"
    seen = tmp_path / "seen"
    stub.write_text(
        "#!/bin/sh\nunset GIT_DIR\n"
        f'echo "$4" > {seen}\n'
        f'cd {host} && git fetch --quiet {q} "$6" && '
        "git rev-parse --quiet --verify FETCH_HEAD > /dev/null\n"
    )
    stub.chmod(0o755)
    update = q / "hooks" / "update"
    update.write_text(update.read_text().replace("exec /tools/bin/land", f"exec {stub}"))

    ws = tmp_path / "ws"
    subprocess.run(["git", "clone", "-q", str(host), str(ws)], check=True)
    (ws / "f.txt").write_text("y")
    subprocess.run(["git", "add", "."], cwd=ws, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "work"],
        cwd=ws, check=True,
    )
    push = subprocess.run(
        ["git", "push", str(q), "HEAD:refs/heads/feat/x"],
        cwd=ws, capture_output=True, text=True,
    )
    assert push.returncode == 0, push.stderr
    assert seen.read_text().strip() == "feat/x"
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "refs/heads/feat/x"],
        cwd=q, capture_output=True, text=True,
    )
    assert probe.returncode != 0, "post-receive must clear the land ref"
    seen.unlink()
    ckpt = subprocess.run(
        ["git", "push", str(q), f"HEAD:{quarantine.checkpoint_ref('s')}"],
        cwd=ws, capture_output=True, text=True,
    )
    assert ckpt.returncode == 0, ckpt.stderr
    assert not seen.exists(), "checkpoint must not run land"
    kept = subprocess.run(
        ["git", "rev-parse", "--verify", quarantine.checkpoint_ref("s")],
        cwd=q, capture_output=True, text=True,
    )
    assert kept.returncode == 0, "checkpoints stay in the quarantine"


def test_delete_session_quarantines(internals, tmp_path):
    host = _host_repo(tmp_path)
    quarantine.ensure_quarantine(
        session_id="S2", repo="app", host_gitdir=host / ".git",
    )
    quarantine.delete_session_quarantines("S2")
    assert not quarantine.session_quarantine_dir("S2").exists()
    quarantine.delete_session_quarantines("S2")


def _hook_argv(tmp_path: Path, q: Path, *opts: str) -> list[str]:
    stub, seen = tmp_path / "argv-stub.sh", tmp_path / "argv"
    stub.write_text(f"#!/bin/sh\nprintf '%s\\0' \"$@\" > {seen}\n")
    stub.chmod(0o755)
    update = q / "hooks" / "update"
    update.write_text(update.read_text().replace("exec /tools/bin/land", f"exec {stub}"))
    env = {"GIT_PUSH_OPTION_COUNT": str(len(opts))}
    env |= {f"GIT_PUSH_OPTION_{i}": o for i, o in enumerate(opts)}
    subprocess.run([str(update), "refs/heads/feat/x", "0" * 40, "a" * 40], env=env, check=True)
    return seen.read_text().split("\0")[:-1]


@pytest.mark.timeout(10)
def test_update_hook_argv_matches_land_parser(internals, tmp_path):
    host = _host_repo(tmp_path)
    q = quarantine.ensure_quarantine(session_id="S5", repo="app", host_gitdir=host / ".git")
    raw = parser_for(LandTool.argv, LandInput)

    def parse(argv: list[str]) -> LandInput:
        out = raw(argv)
        assert isinstance(out, LandInput)
        return out

    plain = parse(_hook_argv(tmp_path, q))
    assert (plain.repo, plain.branch, plain.sha) == ("app", "feat/x", "a" * 40)
    assert (plain.message, plain.mode) == ("", "")
    argv = _hook_argv(tmp_path, q, "mode=fast-forward", "message=hi there")
    assert [a for a in argv if a.startswith("--")] == ["--repo", "--branch", "--sha", "--message", "--mode"]
    full = parse(argv)
    assert (full.mode, full.message) == ("fast-forward", "hi there")
    described = parse(_hook_argv(tmp_path, q, "description=## Why", "description=", "description=- a"))
    assert described.description == "## Why\n\n- a"
