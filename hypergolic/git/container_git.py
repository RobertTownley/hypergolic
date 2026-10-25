from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from sqlalchemy import select

import hypergolic.config.settings as config
from hypergolic.sessions import session_rows
from hypergolic.db.engine import get_db
from hypergolic.db.models import DBSandbox
from hypergolic.git.commands import GitResult
from hypergolic.git.sandbox_repo import container_name
from hypergolic.harness.app.state import get_app
from hypergolic.sandbox.model.constants import (
    HARNESS_MOUNT,
    SANDBOX_TOOL_ID,
    SHARED_MOUNT,
    WORKSPACE_MOUNT,
)

GIT_EXEC_TIMEOUT = 120


class SandboxRepoUnavailable(Exception):
    def __init__(self, workspace: Path):
        super().__init__(
            f"The repo for {workspace} lives inside the session's sandbox, "
            "which is not running. Start the sandbox (run any session "
            "command) to inspect or change its git state."
        )
        self.workspace = workspace


def _session_for_workspace(workspace: Path) -> tuple[str, str] | None:
    found = session_rows.find(worktree_path=str(workspace))
    return (found[0].id, found[0].project_id) if found else None


def _harness_session_for(cwd: Path) -> tuple[str, str] | None:
    if cwd.name != "harness" or cwd.parent.parent != config.sessions_internals_root():
        return None
    session_id = cwd.parent.name
    row = session_rows.fetch(session_id)
    return None if row is None else (session_id, row.project_id)


def _shared_session_for(cwd: Path) -> tuple[str, str] | None:
    if cwd.name != "shared" or cwd.parent.parent != config.sessions_internals_root():
        return None
    session_id = cwd.parent.name
    row = session_rows.fetch(session_id)
    return None if row is None else (session_id, row.project_id)


def _classify(cwd: Path) -> tuple[str, str, str] | None:
    ids = _session_for_workspace(cwd)
    if ids is not None:
        return WORKSPACE_MOUNT, ids[0], ids[1]
    ids = _harness_session_for(cwd)
    if ids is not None:
        return HARNESS_MOUNT, ids[0], ids[1]
    ids = _shared_session_for(cwd)
    if ids is not None:
        return SHARED_MOUNT, ids[0], ids[1]
    return None


def _running_sandbox_row(session_id: str, project_id: str):
    stmt = (
        select(DBSandbox)
        .where(DBSandbox.tool_id == SANDBOX_TOOL_ID)
        .where(DBSandbox.status == "running")
        .where(DBSandbox.session_id == session_id)
    )
    with get_db() as db:
        return db.execute(stmt).scalars().first()


def _container_for(session_id: str, project_id: str) -> str | None:
    sandbox = _running_sandbox_row(session_id, project_id)
    if sandbox is None or not sandbox.compose_project:
        return None
    try:
        project = get_app().find_project(project_id)
    except RuntimeError:
        return None
    sandbox_model = project.resolved_sandbox if project else None
    if sandbox_model is None:
        return None
    service = next(
        (c.id for c in sandbox_model.containers if not c.skip_workspace_mount),
        None,
    )
    if service is None:
        return None
    return container_name(sandbox.compose_project, service)


def routes_to_sandbox(cwd: Path | None) -> bool:
    if cwd is None or not cwd.is_dir():
        return False
    dotgit = cwd / ".git"
    if dotgit.is_dir():
        return False
    if not dotgit.exists():
        return _session_for_workspace(cwd) is not None
    return not _gitdir_pointer_resolves(dotgit)


def _gitdir_pointer_resolves(dotgit: Path) -> bool:
    try:
        text = dotgit.read_text()
    except OSError:
        return False
    if not text.startswith("gitdir:"):
        return False
    target = text.removeprefix("gitdir:").strip()
    return bool(target) and Path(target).exists()


def _argv(workspace: Path, args: tuple[str, ...]) -> list[str]:
    route = _classify(workspace)
    if route is None:
        raise SandboxRepoUnavailable(workspace)
    mount, session_id, project_id = route
    container = _container_for(session_id, project_id)
    if container is None:
        raise SandboxRepoUnavailable(workspace)
    return ["docker", "exec", "-i", container, "git", "-C", mount, *args]


def run_container_git(
    workspace: Path, *args: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            _argv(workspace, args),
            capture_output=True, text=True, timeout=GIT_EXEC_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise SandboxRepoUnavailable(workspace) from None


async def async_run_container_git(workspace: Path, *args: str):
    proc = await asyncio.create_subprocess_exec(
        *_argv(workspace, args),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        raw_out, raw_err = await asyncio.wait_for(
            proc.communicate(), timeout=GIT_EXEC_TIMEOUT,
        )
    except TimeoutError:
        proc.kill()
        raise SandboxRepoUnavailable(workspace) from None
    return GitResult(
        returncode=proc.returncode or 0,
        stdout=raw_out.decode(errors="replace"),
        stderr=raw_err.decode(errors="replace"),
    )
