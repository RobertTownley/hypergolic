"""The repo convergence loop: check → repair → verify each repo slot,
idempotently, on creation and after every ``compose up``. A missing clone is
created, an existing gitdir healed, and every repo verified usable; results
are recorded per session (:mod:`.repo_report`). See docs/sandbox-lifecycle.md.
"""

from __future__ import annotations

import asyncio

import logging
from pathlib import Path

from hypergolic.git.commands import async_run_git_command
from hypergolic.git.eval_source import eval_source_path, seed_eval_source
from hypergolic.git.quarantine import quarantine_mount
from hypergolic.git.sandbox_repo import (
    REPO_APP,
    REPO_HARNESS,
    REPO_SHARED,
    clone_script,
    heal_script,
    repo_opens,
)
from hypergolic.git.harness_repo import harness_base_branch
from hypergolic.sandbox.shared import shared_dir
from hypergolic.harness.app.state import get_app
from hypergolic.harness.project import Project
from hypergolic.sandbox.manager.exec import exec_in_sandbox
from hypergolic.sandbox.manager.compose_env import settings_harness_gitdir
from hypergolic.sandbox.manager.repo_report import (
    RepoProvisionError,
    RepoStep,
    record_report,
)
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.sandbox.manager.workspace import host_git_identity, workspace_service
from hypergolic.sandbox.model.constants import (
    HARNESS_MOUNT,
    SANDBOX_TOOL_ID,
    SHARED_MOUNT,
    WORKSPACE_MOUNT,
)
from hypergolic.schemas import Session

logger = logging.getLogger(__name__)

#: Covers a cold checkout of a large working tree through the bind mount.
CLONE_TIMEOUT_SECONDS = 1800

#: Heal/verify never do clone-scale work and can run under the start lock,
#: so their budget must not stall the session for long.
HEAL_TIMEOUT_SECONDS = 120

#: Openability, not existence: a `.git` pointer whose gitdir volume died must
#: route to clone_script's rebuild branch, not to heal.
APP_OPENS_PROBE = repo_opens(WORKSPACE_MOUNT)





def _load_session(session_id: str) -> Session:
    # cycle: sessions.operations -> git.worktree_lifecycle -> this module
    from hypergolic.sessions.operations import load_session

    return load_session(session_id)


def _checkout_name(session: Session) -> str:
    """The /app checkout's branch name: the base as the session sees it
    (a child of a live parent branch sees the parent's own base)."""
    from hypergolic.git.parent_land import visible_base  # cycle

    return visible_base(session) or session.base_branch or "main"


def _find_project(project_id: str) -> Project | None:
    return get_app().find_project(project_id)




async def provision_sandbox(session: Session, project: Project) -> list[RepoStep]:
    """The convergence loop: check → repair → verify each repo slot.

    Idempotent and self-healing; runs on creation and after every ``compose
    up``. Never raises — failures land in the returned steps, the per-session
    report, and the log.
    """
    steps = [
        await _ensure_app_repo(session, project),
        await _ensure_harness_repo(session, project),
        await _ensure_shared_repo(session, project),
    ]
    record_report(session.id, steps)
    for step in steps:
        if step.ok is False:
            logger.warning(
                "Repo convergence failed: session=%s repo=%s action=%s: %s",
                session.id, step.repo, step.action, step.detail,
            )
    return steps


async def _identity() -> dict[str, str]:
    name, email = await asyncio.to_thread(host_git_identity)
    return {"user_name": name, "user_email": email}


async def _exec_clone(
    session: Session, project: Project, script: str,
    timeout: int = CLONE_TIMEOUT_SECONDS,
):
    # project_root=None disables exec's dead-container recovery, which would
    # re-enter the caller's _start_lock and deadlock; a down container
    # degrades to a failed RepoStep instead.
    return await exec_in_sandbox(
        session_id=session.id,
        tool_id=SANDBOX_TOOL_ID,
        command=script,
        timeout=timeout,
        project_root=None,
        container=workspace_service(project),
    )


async def _run_step(
    session: Session, project: Project, *, repo: str, action: str, script: str,
    fix: str, timeout: int = CLONE_TIMEOUT_SECONDS,
) -> RepoStep:
    try:
        result = await _exec_clone(session, project, script, timeout)
    except SandboxError as e:
        return RepoStep(repo, action, False, str(e), fix)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        return RepoStep(repo, action, False, detail, fix)
    return RepoStep(repo, action, True, "converged and verified")


async def _ensure_app_repo(session: Session, project: Project) -> RepoStep:
    if not session.base_branch or not session.worktree_path:
        return RepoStep(REPO_APP, "skip", None, "session has no workspace")
    host_gitdir = Path(project.path) / ".git"
    src = eval_source_path(session.id) if session.conducted_by else host_gitdir
    fix = "check the host repo and quarantine mounts; rerun run_readiness_probes"
    try:
        probe = await _exec_clone(session, project, APP_OPENS_PROBE, HEAL_TIMEOUT_SECONDS)
    except SandboxError as e:
        return RepoStep(REPO_APP, "heal", False, str(e), fix)
    if probe.returncode == 0:
        script = heal_script(
            workdir=WORKSPACE_MOUNT, src=str(src),
            push_url=quarantine_mount(REPO_APP),
            pre_commit=project.pre_commit, **await _identity(),
        )
        return await _run_step(
            session, project, repo=REPO_APP, action="heal", script=script, fix=fix,
            timeout=HEAL_TIMEOUT_SECONDS,
        )
    from hypergolic.sandbox.manager.repo_creation import _resolve_base_ref  # cycle

    try:
        base_ref = await _resolve_base_ref(session, project)
    except RepoProvisionError as e:
        return RepoStep(REPO_APP, "clone", False, str(e), fix)
    branch = await asyncio.to_thread(_checkout_name, session)
    pin = session.repo_pins.get(REPO_APP)
    if session.conducted_by:
        try:
            await _seed_eval_source(session, project, base_ref, branch, pin)
        except Exception as e:
            return RepoStep(REPO_APP, "clone", False, f"eval source: {e}", fix)
        base_ref, pin = f"refs/heads/{branch}", None
    script = clone_script(
        repo=REPO_APP, workdir=WORKSPACE_MOUNT, src=str(src),
        base_ref=base_ref, branch=branch,
        push_url=quarantine_mount(REPO_APP),
        pre_commit=project.pre_commit, pin=pin,
        **await _identity(),
    )
    return await _run_step(
        session, project, repo=REPO_APP, action="clone", script=script, fix=fix,
    )


async def _seed_eval_source(
    session: Session, project: Project, base_ref: str, branch: str, pin: str | None,
) -> None:
    host = Path(project.path)
    rev = await async_run_git_command(
        "rev-parse", "--verify", "--quiet", f"{pin or base_ref}^{{commit}}",
        cwd=host, check=True,
    )
    await seed_eval_source(session.id, host, branch, rev.stdout.strip())


async def _ensure_harness_repo(session: Session, project: Project) -> RepoStep:
    """A session without /harness can still do project work: report, don't raise."""
    gitdir = settings_harness_gitdir()
    if gitdir is None:
        return RepoStep(REPO_HARNESS, "skip", None, "harness is not git-controlled")
    base = await asyncio.to_thread(harness_base_branch)
    if base is None:
        return RepoStep(
            REPO_HARNESS, "skip", None,
            "harness repo unusable (detached HEAD / no commits)",
        )
    return await _ensure_aux_repo(
        session, project, repo=REPO_HARNESS, workdir=HARNESS_MOUNT,
        gitdir=gitdir, branch=base,
        fix="check the harness gitdir mount; a /harness-less session still works",
    )


async def _ensure_shared_repo(session: Session, project: Project) -> RepoStep:
    gitdir = shared_dir(project.id) / ".git"
    if not gitdir.is_dir():
        return RepoStep(REPO_SHARED, "skip", None, "project shared repo has no gitdir")
    return await _ensure_aux_repo(
        session, project, repo=REPO_SHARED, workdir=SHARED_MOUNT,
        gitdir=gitdir, branch="main",
        fix="check the project shared repo under ~/.hypergolic_internals/projects",
    )


async def _ensure_aux_repo(
    session: Session, project: Project, *,
    repo: str, workdir: str, gitdir: Path, branch: str, fix: str,
) -> RepoStep:
    script = clone_script(
        repo=repo, workdir=workdir, src=str(gitdir),
        base_ref=f"refs/heads/{branch}", branch=branch,
        push_url=quarantine_mount(repo), pin=session.repo_pins.get(repo),
        **await _identity(),
    )
    return await _run_step(
        session, project, repo=repo, action="ensure", script=script, fix=fix,
    )
