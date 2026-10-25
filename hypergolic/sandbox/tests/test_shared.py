"""Tests for the per-project persistent /shared dir + seeded starter CLI."""

import hypergolic.config.settings as config
import hypergolic.sandbox.shared as shared
from hypergolic.sandbox.shared import (
    SHARED_CLI_NAME,
    _slug,
    ensure_shared_dir,
    shared_dir,
)


def test_slug_sanitizes_and_disambiguates():
    assert _slug("my-project_1").startswith("my-project_1-")
    assert _slug("a/b:c d").startswith("a-b-c-d-")
    # Distinct ids that sanitize to the same prefix get distinct slugs.
    assert _slug("a/b") != _slug("a-b")
    # An all-unsafe id still yields a stable, non-empty slug.
    assert _slug("///")


def test_shared_dir_is_per_project_under_internals(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "INTERNALS_DIR", tmp_path)
    d = shared_dir("demo")
    assert d.parent.parent == tmp_path / "projects"
    assert d.name == "shared"
    assert d.parent.name.startswith("demo-")


def test_ensure_seeds_cli_once(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "INTERNALS_DIR", tmp_path)
    path = ensure_shared_dir("demo")
    cli = path / SHARED_CLI_NAME
    assert path.is_dir()
    assert cli.is_file()
    body = cli.read_text()
    assert "import argparse" in body
    assert "# dependencies" not in body  # stdlib-only: no cold-start installs
    assert "uv run /shared/main.py --help" in body

    # Re-running never clobbers an evolved CLI.
    cli.write_text("# customized by the agent\n")
    again = ensure_shared_dir("demo")
    assert again == path
    assert cli.read_text() == "# customized by the agent\n"


def test_ensure_creates_repo_with_in_mount_gitdir(monkeypatch, tmp_path):
    import subprocess

    monkeypatch.setattr(config, "INTERNALS_DIR", tmp_path)
    path = ensure_shared_dir("demo")
    # A real `.git` dir inside the mount: in-container git must resolve it.
    assert (path / ".git").is_dir()
    head = subprocess.run(
        ["git", "-C", str(path), "log", "--format=%s"],
        capture_output=True, text=True,
    )
    assert head.stdout.strip() == "Initial shared state"
    # Re-running adopts/heals nothing and adds no commits.
    assert ensure_shared_dir("demo") == path
    again = subprocess.run(
        ["git", "-C", str(path), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True,
    )
    assert again.stdout.strip() == "1"


def test_distinct_projects_get_distinct_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "INTERNALS_DIR", tmp_path)
    assert ensure_shared_dir("a") != ensure_shared_dir("b")


def test_existing_git_is_left_alone(monkeypatch, tmp_path):
    """A pre-existing `.git` (agent-era, or prior run) is never adopted or
    healed on the host — host git must not run through agent-writable hooks."""
    import subprocess

    monkeypatch.setattr(config, "INTERNALS_DIR", tmp_path)
    path = shared.shared_dir("demo")
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    ensure_shared_dir("demo")
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True,
    )
    assert head.returncode != 0  # no host-made commits in a repo we didn't create
