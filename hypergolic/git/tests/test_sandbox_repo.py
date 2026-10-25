import subprocess

import pytest

from hypergolic.git.sandbox_repo import (
    clone_script,
    container_name,
    heal_script,
    hypergolic_ref,
    repo_opens,
    session_gitdir,
)


def test_paths():
    assert session_gitdir("app") == "/var/git/app.git"
    assert hypergolic_ref("acme", "main-ABC") == "refs/hypergolic/acme/main-ABC"
    assert container_name("hg-s1-cmd", "dev") == "hg-s1-cmd-dev-1"


def _script(**kw):
    return clone_script(
        repo="app", workdir="/app", src="/host/repo/.git",
        base_ref="refs/heads/main", branch="main",
        push_url="/quarantine/app.git", **kw,
    )


def test_clone_script_clones_shared_split_urls_when_missing():
    s = _script()
    assert f"if {repo_opens('/app')}; then" in s
    assert "elif [ -e /app/.git ]; then" in s
    assert "--shared" in s
    assert "--separate-git-dir=/var/git/app.git" in s
    assert "/host/repo/.git /app" in s
    assert "fetch --quiet origin refs/heads/main" in s
    assert "checkout --quiet -B main FETCH_HEAD" in s
    assert "remote set-url --push origin /quarantine/app.git" in s
    assert "config branch.main.merge refs/heads/main" in s
    assert "hooks" not in s


def test_heal_script_noops_without_clone_and_never_clones():
    s = heal_script(workdir="/app", src="/h/.git", push_url="/q/app.git")
    assert "[ -e /app/.git ] || exit 0" in s
    assert "clone" not in s


def test_clone_script_installs_pre_commit_hook():
    s = _script(pre_commit="uv run pytest -q")
    assert "/var/git/app.git/hooks/pre-commit" in s
    assert "uv run pytest -q" in s


def test_top_level_clone_keeps_default_tracking():
    assert "remote.origin.fetch" not in _script()


def test_child_clone_tracks_its_parent_checkpoint_as_origin_branch():
    s = clone_script(
        repo="app", workdir="/app", src="/host/repo/.git",
        base_ref="refs/hypergolic/p/main-P1", branch="main",
        push_url="/quarantine/app.git",
    )
    assert "config --add remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'" in s
    assert "config --add remote.origin.fetch '^refs/heads/main'" in s
    assert "config --add remote.origin.fetch +refs/hypergolic/p/main-P1:refs/remotes/origin/main" in s
    assert s.index("^refs/heads/main") < s.rindex("fetch --quiet origin")


def _git(*args, cwd, env=None):
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.mark.timeout(10)
def test_heal_script_revives_relic_clone(tmp_path):
    env = {"HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    host = tmp_path / "host-old"
    host.mkdir()
    _git("init", "-q", "-b", "main", cwd=host)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
         "--allow-empty", "-m", "seed", cwd=host)

    wd, gitdir = tmp_path / "wd", tmp_path / "gitdir" / "app.git"
    gitdir.parent.mkdir()
    _git("clone", "-q", "--shared", "--no-checkout",
         f"--separate-git-dir={gitdir}", str(host / ".git"), str(wd), cwd=tmp_path, env=env)

    host.rename(tmp_path / "host-new")
    src = tmp_path / "host-new" / ".git"
    _git("remote", "set-url", "origin", "/host-repos/app.git", cwd=wd, env=env)
    (gitdir / "objects" / "info" / "alternates").write_text("/host-repos/app.git/objects\n")
    assert subprocess.run(
        ["git", "fetch", "origin"], cwd=wd, env=env, capture_output=True,
    ).returncode != 0

    script = heal_script(
        workdir=str(wd), src=str(src), push_url=str(tmp_path / "q" / "app.git"),
        user_name="User", user_email="u@example.com",
    )
    r = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    assert _git("remote", "get-url", "origin", cwd=wd, env=env) == str(src)
    assert _git("remote", "get-url", "--push", "origin", cwd=wd, env=env) == str(
        tmp_path / "q" / "app.git"
    )
    assert (gitdir / "objects" / "info" / "alternates").read_text().strip() == f"{src}/objects"
    _git("fetch", "origin", cwd=wd, env=env)
    assert _git("config", "--global", "user.email", cwd=tmp_path, env=env) == "u@example.com"


def test_clone_script_pin_checks_out_sha_instead_of_fetch_head():
    s = _script(pin="c" * 40)
    assert f"checkout --quiet -B main {'c' * 40}" in s
    assert "checkout --quiet -B main FETCH_HEAD" not in s
    assert "fetch --quiet origin refs/heads/main" in s


@pytest.mark.timeout(10)
def test_clone_script_rebuilds_repo_around_dangling_gitdir_pointer(tmp_path):
    env = {"HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    host = tmp_path / "host"
    host.mkdir()
    _git("init", "-q", "-b", "main", cwd=host)
    (host / "kept.txt").write_text("base\n")
    _git("add", ".", cwd=host)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "seed", cwd=host)

    wd, gitdir = tmp_path / "wd", tmp_path / "var-git" / "app.git"
    wd.mkdir()
    gitdir.parent.mkdir()
    (wd / ".git").write_text(f"gitdir: {gitdir}\n")
    (wd / "kept.txt").write_text("edited\n")
    (wd / "new.txt").write_text("work\n")

    script = clone_script(
        repo="app", workdir=str(wd), src=str(host / ".git"),
        base_ref="refs/heads/main", branch="main",
        push_url=str(tmp_path / "q" / "app.git"),
        user_name="User", user_email="u@example.com",
    )
    script = script.replace("/var/git/app.git", str(gitdir))
    r = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    assert (wd / "kept.txt").read_text() == "edited\n"
    assert (wd / "new.txt").read_text() == "work\n"
    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=wd, env=env) == "main"
    status = _git("status", "--porcelain", cwd=wd, env=env)
    assert "M kept.txt" in status and "?? new.txt" in status
