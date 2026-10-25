"""Generating the ``/tools`` tree a session's sandbox mounts read-only.

``/tools``, not ``/skills``: a command can come from a skill, a role, a workflow
state, a project, or an MCP server, so keying the tree on "skill" would misfile
most of them. It is keyed on the command, which is what the agent actually types.

The tree holds no source. ``/harness`` and the package are already mounted, so
copying implementation would only create drift — ``/tools`` is the *interface*,
those are the *implementation*, and ``<name>/source`` is a symlink so what the
agent reads is literally the file that will run.

Generated per session, because the command set depends on project, role, active
workflow state, and enabled MCP servers. The tree is a bind mount of a host
directory, so rewriting it in place is visible to a running container
immediately; there is no remount step.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from hypergolic.commands.docs import index_markdown, readme
from hypergolic.commands.shim import SHIM_SOURCE
from hypergolic.config.settings import HARNESS_DIR, session_internals_dir
from hypergolic.harness.primitives.tool import Tool
from hypergolic.commands.validate import assert_valid
from hypergolic.sandbox.model.constants import HARNESS_MOUNT, PACKAGE_MOUNT

logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def tools_dir(session_id: str) -> Path:
    """Host directory backing ``/tools`` for a session (not created)."""
    return session_internals_dir(session_id) / "tools"


def _container_source_path(host_path: Path) -> str | None:
    """Translate a host source path to where the container can see the same file.

    Only two trees are mounted, so anything outside them has no in-container
    path and gets no symlink rather than a dangling one.
    """
    for root, mount in ((HARNESS_DIR, HARNESS_MOUNT), (_PACKAGE_ROOT, PACKAGE_MOUNT)):
        try:
            relative = host_path.resolve().relative_to(Path(root).resolve())
        except ValueError:
            continue
        return f"{mount}/{relative}"
    return None


def _clear(root: Path) -> None:
    """Empty the tree without replacing the directory the container has open."""
    for child in root.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _write_command(root: Path, command: Tool) -> None:
    directory = root / command.id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "README.md").write_text(readme(command))

    source = command.source_file()
    link = directory / "source"
    if link.is_symlink() or link.exists():
        link.unlink()
    if source is not None:
        target = _container_source_path(source)
        if target is not None:
            link.symlink_to(target)

    if command.invocable:
        shim = root / "bin" / command.id
        shim.write_text(SHIM_SOURCE)
        shim.chmod(0o755)


def materialize(session_id: str, commands: dict[str, Tool]) -> Path:
    """Write the session's ``/tools`` tree and return its host path.

    Rebuilt from scratch each time: a command that disappeared (a disabled MCP
    server, a workflow state left behind) must lose its shim, and reconciling
    deletions incrementally is more code than rewriting a few dozen small files.

    The root directory itself survives, and must: compose bind-mounts it, so
    replacing it would swap the inode under a running container and leave
    ``/tools`` permanently empty inside the sandbox.
    """
    assert_valid(list(commands.values()))

    root = tools_dir(session_id)
    root.mkdir(parents=True, exist_ok=True)
    _clear(root)
    (root / "bin").mkdir(parents=True, exist_ok=True)

    for command in commands.values():
        _write_command(root, command)

    (root / "index.md").write_text(index_markdown(commands))
    return root


def ensure_materialized(session_id: str, commands: dict[str, Tool]) -> str | None:
    """Materialize, returning a diagnostic instead of raising.

    A session whose ``/tools`` could not be written is degraded, not dead: the
    sandbox shell still works, so the caller reports the problem to the agent
    rather than taking the turn down. Silence is the one unacceptable outcome —
    a missing shim otherwise looks like a missing capability.
    """
    try:
        materialize(session_id, commands)
    except Exception as exc:
        logger.warning(
            "Failed to materialize /tools for session %s", session_id, exc_info=True
        )
        return f"Tool interface (/tools) could not be generated: {exc}"
    return None


def discard(session_id: str) -> None:
    _FINGERPRINTS.pop(session_id, None)
    root = tools_dir(session_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


#: session_id -> fingerprint of the command set last written. Rewriting a few
#: dozen small files on every exec would be wasteful and would churn mtimes the
#: agent may be reading; the fingerprint makes regeneration happen exactly when
#: the session's capability actually changes.
_FINGERPRINTS: dict[str, str] = {}


def fingerprint(commands: dict[str, Tool]) -> str:
    parts = [
        "\x1f".join(
            (
                command.id,
                command.description,
                command.usage,
                command.domain,
                command.origin,
                ",".join(command.tags),
                "1" if command.invocable else "0",
                str(len(command.guidance)),
            )
        )
        for _, command in sorted(commands.items())
    ]
    return hashlib.sha256("\x1e".join(parts).encode()).hexdigest()


def sync(session_id: str, commands: dict[str, Tool]) -> str | None:
    """Materialize ``/tools`` if the session's command set changed.

    Returns a diagnostic when generation failed, ``None`` on success.
    """
    current = fingerprint(commands)
    if _FINGERPRINTS.get(session_id) == current and tools_dir(session_id).is_dir():
        return None
    problem = ensure_materialized(session_id, commands)
    if problem is None:
        _FINGERPRINTS[session_id] = current
    return problem
