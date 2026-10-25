"""Per-project persistent shared directory mounted at ``/shared``.

Every container that mounts the workspace gets a per-session clone of this
repo mounted read-write at :data:`hypergolic.sandbox.model.SHARED_MOUNT`.
Unlike the ephemeral worktree and the per-session sandbox, the underlying repo
persists across sessions and is shared by every version of the project, so
successive sessions can accumulate and reuse project-specific operational
knowledge and tooling.
The host directory here is the *landing repo*: each session works in its own
/shared clone (provisioned like /app and /harness) and lands edits with
``git push origin main`` — ungated by default, so "commit then push" is the
whole flow. Other sessions see an edit once it lands.

The directory is seeded on first use with a stdlib-only argparse CLI at
``/shared/main.py`` that the agent extends over time (test runners, service start/stop, SQL
helpers, etc.) and discovers via ``uv run /shared/main.py --help``.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

import hypergolic.config.settings as config

logger = logging.getLogger(__name__)

SHARED_CLI_NAME = "main.py"

_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."

# Kept on one source line: a literal `# /// script` line start would make ty
# treat this module as a PEP 723 script and drop the project search path.
_SEED_HEADER = '#!/usr/bin/env -S uv run --quiet\n# /// script\n# requires-python = ">=3.11"\n# ///\n'

_SEED_CLI = _SEED_HEADER + '''\
"""Project shared CLI.

This file lives on a host-backed volume mounted read-write at /shared, shared
across every session and version of this project. Add commands here for tasks
that recur or benefit from captured exploration -- running tests/linters/type
checkers, starting and stopping processes, hitting a running service, executing
SQL inside the container, and so on. List what is available with:

    uv run /shared/main.py --help

Files at the top of /shared are indexed by `apropos`, which reads each file's
leading comment or docstring: a script whose first line says what it is for gets
found by a later session, and one without a header does not. A subdirectory is
only indexed if it holds a README.md, so file things away in directories that
document themselves -- otherwise `apropos` never sees them.

Keep this script stdlib-only: with zero dependencies, `uv run` starts it
instantly on cold containers with no install noise, and its plain-ASCII help
stays cheap to read. A command that truly needs a library can shell out to
`uv run --with <dep> ...` for just that step.
"""

import argparse


def hello() -> None:
    print(
        "This project's shared CLI has no commands yet. "
        "Add useful ones to /shared/main.py."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Shared, persistent CLI for this project. Extend it as you learn.",
        epilog=(
            "`apropos` indexes every file at the top of /shared, and a subdirectory "
            "only if it holds a README.md. It reads each file's first docstring or "
            "comment: give anything you leave here a one-line header saying what it "
            "is for, or a later session will not find it."
        ),
    )
    subparsers = parser.add_subparsers(required=True)

    hello_parser = subparsers.add_parser(
        "hello", help="Placeholder command. Replace with real project helpers."
    )
    hello_parser.set_defaults(func=hello)

    args = parser.parse_args()
    args.func()


if __name__ == "__main__":
    main()
'''


KNOWLEDGE_DIR_NAME = "knowledge"

#: Harness-improvement proposals filed by concluding-time distillation
#: sessions (see dispatch/knowledge.py); surfaced at session start and
#: triaged via the harness-engineering skill.
PROPOSALS_DIR_NAME = "harness/proposals"

_SEED_KNOWLEDGE_README = """\
# Knowledge Base

Durable project+user facts accumulated across sessions. This index is injected
into every session's prompt: keep it a short map, detail one hop deeper.
Before adding or curating anything here, run `activate_skill knowledge-base`
for the conventions.

## Bootstrap (new base — replace this section with a real index as you fill it)

Nothing recorded yet. Seed the base from what already exists:

- `git log` — commit-message style, merge/release patterns, active areas.
- Repo code and configs — stack, layout, build/test/run commands, conventions
  (lint rules, module structure) a session would otherwise rediscover.
- Integrations — CI, deploy targets, external services and how to reach them.
- This session — user corrections, preferences, denied tool calls and why.

## Index

(empty — one line per entry, grouped by directory)
"""


def _slug(project_id: str) -> str:
    """Filesystem-safe, collision-free dir name for ``project_id``.

    The readable prefix is sanitized for the filesystem; a short hash of the
    raw id is appended so distinct ids that sanitize to the same string (e.g.
    ``a/b`` and ``a-b``) never share a directory.
    """
    cleaned = "".join(c if c in _SAFE else "-" for c in project_id).strip("-.")
    digest = hashlib.sha1(project_id.encode()).hexdigest()[:8]
    return f"{cleaned}-{digest}" if cleaned else digest


def session_shared_workspace(session_id: str) -> Path:
    """Host source dir of the session's /shared bind mount (files only; the
    clone's gitdir lives in the sandbox's volume)."""
    return config.session_internals_dir(session_id) / "shared"


def shared_dir(project_id: str) -> Path:
    """Host path backing ``/shared`` for ``project_id`` (not created)."""
    return config.INTERNALS_DIR / "projects" / _slug(project_id) / "shared"


def ensure_shared_dir(project_id: str) -> Path:
    """Create the project's shared dir, seeding the starter CLI if absent."""
    path = shared_dir(project_id)
    path.mkdir(parents=True, exist_ok=True)
    cli = path / SHARED_CLI_NAME
    if not cli.exists():
        cli.write_text(_SEED_CLI)
    knowledge_readme = path / KNOWLEDGE_DIR_NAME / "README.md"
    if not knowledge_readme.exists():
        knowledge_readme.parent.mkdir(exist_ok=True)
        knowledge_readme.write_text(_SEED_KNOWLEDGE_README)
    ensure_shared_repo(path)
    return path


def ensure_shared_repo(path: Path) -> None:
    """Bring a freshly created shared dir under git.

    The ``.git`` directory lives *inside* the rw mount: sessions run real git
    in /shared (commit straight to main), so the repo must resolve in-container.
    Host git only ever touches it here, at creation time, before any agent has
    written to the dir — an existing ``.git`` (agent-era, or from a prior run)
    is never adopted or healed on the host. Plain subprocess git, not
    ``run_git_command``: once ``.git`` exists this dir routes to container
    git, and this is the one legitimate pre-container moment.
    """
    if (path / ".git").exists():
        return
    ident = ["-c", "user.email=hypergolic@localhost", "-c", "user.name=Hypergolic"]
    for args in (
        ["init", "-b", "main", "."],
        [*ident, "add", "-A"],
        [*ident, "commit", "-m", "Initial shared state"],
    ):
        result = subprocess.run(
            ["git", "-C", str(path), *args], capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "shared repo init failed in %s: git %s: %s",
                path, args[0], result.stderr.strip() or result.stdout.strip(),
            )
            return
