from __future__ import annotations

import asyncio

import logging
from pathlib import Path

from hypergolic.git.commands import async_run_git_command
from hypergolic.git.quarantine import checkpoint_ref, fetch_quarantine_ref
from hypergolic.git.sandbox_repo import REPO_APP, hypergolic_ref
from hypergolic.harness.project import Project
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sandbox.manager.exec import exec_in_sandbox
from hypergolic.sandbox.manager.repo_report import RepoProvisionError
from hypergolic.sandbox.manager.repo_provision import (
    APP_OPENS_PROBE,
    CLONE_TIMEOUT_SECONDS,
    _find_project,
    _load_session,
    provision_sandbox,
)
from hypergolic.sandbox.manager.workspace import session_container, workspace_service
from hypergolic.sandbox.manager.start import needs_start, start_sandbox
from hypergolic.sandbox.manager.types import SandboxError, SandboxUnavailableError
from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID, WORKSPACE_MOUNT
from hypergolic.sandbox.tool.project_tool import write_compose
from hypergolic.schemas import Session

logger = logging.getLogger(__name__)

async def _resolve_base_ref(session: Session, project: Project) -> str:
    host_repo = Path(project.path)
    base = session.base_branch
    assert base is not None
    probe = await async_run_git_command(
        "rev-parse", "--verify", "--quiet", f"refs/heads/{base}", cwd=host_repo,
    )
    if probe.returncode == 0:
        return f"refs/heads/{base}"
    if not session.parent_id:
        raise RepoProvisionError(f"Base `{base}` is not a host branch.")
    ref = await _checkpoint_parent_branch(session.parent_id, base, host_repo, project)
    if ref is None:
        raise RepoProvisionError(
            f"Base `{base}` is not a host branch and could not be "
            "checkpointed out of the parent session's sandbox."
        )
    return ref


async def _checkpoint_parent_branch(
    parent_id: str, branch: str, host_repo: Path, project: Project,
) -> str | None:
    parent = _load_session(parent_id)
    src = "HEAD" if branch == parent.worktree_branch else f"refs/heads/{branch}"
    parent_project = _find_project(parent.project_id)
    if parent_project is None:
        return None
    if await session_container(parent_id, parent_project) is None:
        return None
    push = await exec_in_sandbox(
        session_id=parent_id,
        tool_id=SANDBOX_TOOL_ID,
        command=(
            f"git -C {WORKSPACE_MOUNT} push --quiet origin "
            f"+{src}:{checkpoint_ref(branch)}"
        ),
        timeout=CLONE_TIMEOUT_SECONDS,
        project_root=parent.worktree_path,
        container=workspace_service(parent_project),
    )
    if push.returncode != 0:
        logger.warning("Parent checkpoint push failed: %s", push.stderr.strip())
        return None
    ref = hypergolic_ref(project.id, branch)
    result = await fetch_quarantine_ref(
        host_repo=host_repo, session_id=parent_id, repo=REPO_APP,
        src_ref=checkpoint_ref(branch), dst_ref=ref,
    )
    return ref if result.returncode == 0 else None


async def ensure_session_sandbox(session: Session, project: Project) -> None:
    sandbox = project.resolved_sandbox
    if sandbox is None:
        raise SandboxError("this project has sandboxes disabled")
    config_path = await asyncio.to_thread(write_compose, sandbox)
    existing = await sandbox_rows.get(session.id, SANDBOX_TOOL_ID)
    if not needs_start(existing, config_path):
        return
    assert session.worktree_path
    await start_sandbox(
        session_id=session.id,
        tool_id=SANDBOX_TOOL_ID,
        config_path=config_path,
        project_root=session.worktree_path,
    )


async def repair_session_repo_if_broken(session: Session, project: Project) -> None:
    try:
        probe = await exec_in_sandbox(
            session_id=session.id,
            tool_id=SANDBOX_TOOL_ID,
            command=APP_OPENS_PROBE,
            timeout=60,
            project_root=session.worktree_path,
            container=workspace_service(project),
        )
    except (SandboxError, SandboxUnavailableError):
        return
    if probe.returncode == 0:
        return
    await provision_sandbox(session, project)


async def provision_session_repos(session: Session, project: Project) -> None:
    from hypergolic.git.worktree_lifecycle import set_worktree_status

    await ensure_session_sandbox(session, project)
    await asyncio.to_thread(set_worktree_status, session.id, "cloning")
    steps = await provision_sandbox(session, project)
    app = next((s for s in steps if s.repo == REPO_APP), None)
    if app is None or app.ok is not True:
        raise RepoProvisionError(
            f"In-container clone failed:\n{app.detail if app else 'app step missing'}"
        )
