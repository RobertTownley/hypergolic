"""Session-repo plumbing across the sandbox trust boundary.

The session's three repos (/app, /harness, /shared) live in its sandbox.
Committed work becomes host-visible one way: a **checkpoint** — the container
pushes its checkout to the session's quarantine repo under
``refs/hypergolic/checkpoint/<session branch>``, and the host fetches that ref
into the target repo's ``refs/hypergolic/<scope>/<branch>`` namespace. Landing
on a host branch is the gate pipeline's job (:mod:`hypergolic.gates`),
triggered by the agent's own ``git push origin HEAD:<branch>``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import hypergolic.config.settings as config
from hypergolic.git.commands import async_run_git_command
from hypergolic.git.harness_repo import harness_base_branch, harness_session_branch
from hypergolic.git.quarantine import checkpoint_ref, fetch_quarantine_ref
from hypergolic.git.sandbox_repo import REPO_APP, REPO_HARNESS, REPO_SHARED, hypergolic_ref
from hypergolic.harness.project import Project
from hypergolic.sandbox.manager.exec import exec_in_sandbox
from hypergolic.sandbox.manager.workspace import session_container, workspace_service
from hypergolic.sandbox.manager.types import SandboxError, SandboxUnavailableError
from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID
from hypergolic.sandbox.shared import shared_dir
from hypergolic.schemas import Session

logger = logging.getLogger(__name__)

GIT_EXEC_TIMEOUT = 300

#: /shared checkpoints share the app branch name plus this suffix (same
#: reasoning as HARNESS_BRANCH_SUFFIX: one session, distinct ref names).
SHARED_BRANCH_SUFFIX = "-shared"


class SandboxGitError(Exception):
    """A step of the cross-boundary choreography failed."""


@dataclass(frozen=True)
class RepoSlot:
    """One repo of a session's sandbox (app, harness, or shared)."""

    repo: str              # sandbox_repo slot name: gitdir + mount paths
    workdir: str           # container mount of the working tree
    host_repo: Path        # host-side repo the work lands in
    base_branch: str       # branch work lands on (host branch for top-level)
    session_branch: str    # checkpoint ref name (host-side session identity)
    ref_scope: str         # refs/hypergolic/<scope>/<branch> namespace segment


def app_slot(session: Session, project: Project) -> RepoSlot:
    assert session.base_branch
    return RepoSlot(
        repo=REPO_APP,
        workdir="/app",
        host_repo=Path(project.path),
        base_branch=session.base_branch,
        session_branch=session.live_branch(),
        ref_scope=project.id,
    )


def harness_slot(session: Session) -> RepoSlot:
    """The session's /harness clone. Raises SandboxGitError when the harness
    isn't a usable repo (then no clone was provisioned either)."""
    assert session.worktree_branch
    base = harness_base_branch()
    if base is None:
        raise SandboxGitError(
            "~/.hypergolic is not a usable git repo (detached HEAD or no "
            "commits); there is no /harness clone."
        )
    return RepoSlot(
        repo=REPO_HARNESS,
        workdir="/harness",
        host_repo=config.HARNESS_DIR,
        base_branch=base,
        session_branch=harness_session_branch(session.worktree_branch),
        ref_scope="harness",
    )


def shared_slot(session: Session, project: Project) -> RepoSlot:
    assert session.worktree_branch
    return RepoSlot(
        repo=REPO_SHARED,
        workdir="/shared",
        host_repo=shared_dir(project.id),
        base_branch="main",
        session_branch=f"{session.worktree_branch}{SHARED_BRANCH_SUFFIX}",
        ref_scope="shared",
    )


def slot_for(session: Session, project: Project, repo: str) -> RepoSlot:
    if repo == REPO_HARNESS:
        return harness_slot(session)
    if repo == REPO_SHARED:
        return shared_slot(session, project)
    return app_slot(session, project)


async def exec_repo_git(
    session: Session, project: Project, script: str,
    timeout: int = GIT_EXEC_TIMEOUT,
) -> str:
    """Run *script* in the session's workspace container; stdout on success."""
    try:
        result = await exec_in_sandbox(
            session_id=session.id,
            tool_id=SANDBOX_TOOL_ID,
            command=script,
            timeout=timeout,
            project_root=session.worktree_path,
            container=workspace_service(project),
        )
    except (SandboxError, SandboxUnavailableError) as exc:
        raise SandboxGitError(str(exc)) from exc
    if result.returncode != 0:
        raise SandboxGitError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


async def running_container(session: Session, project: Project) -> str:
    """The session's workspace container name; raises when it isn't running."""
    container = await session_container(session.id, project)
    if container is None:
        raise SandboxGitError(
            "The session's sandbox is not running, so its repo is unreachable. "
            "Run any command (e.g. `git status` via cmd) to start it, then retry."
        )
    return container


async def assert_sandbox_worktree_clean(
    session: Session, project: Project, workdir: str = "/app",
) -> None:
    """Raise SandboxGitError unless the in-container worktree is clean."""
    # `set -e` semantics by hand: a failing `git status` must surface as a
    # nonzero exit (SandboxGitError), never read as "clean".
    script = (
        f"cd {workdir} || exit 9\n"
        "st=$(git status --porcelain) || exit 9\n"
        "printf '%s\\n' \"$st\"\n"
        "gd=$(git rev-parse --git-dir) || exit 9\n"
        "for m in MERGE_HEAD REBASE_HEAD CHERRY_PICK_HEAD BISECT_LOG "
        "rebase-merge rebase-apply; do "
        '[ -e "$gd/$m" ] && echo "IN_PROGRESS:$m"; done\n'
        "true"
    )
    out = (await exec_repo_git(session, project, script)).strip()
    if out:
        raise SandboxGitError(
            "The worktree has uncommitted changes or an in-progress "
            f"operation:\n{out}"
        )


async def refresh_session_ref(session: Session, project: Project) -> str:
    """Checkpoint the app checkout into the host's refs/hypergolic namespace."""
    return await refresh_slot_ref(session, project, app_slot(session, project))


async def refresh_slot_ref(
    session: Session, project: Project, slot: RepoSlot, src: str = "HEAD",
) -> str:
    """Checkpoint *slot*: container pushes whatever *src* (default HEAD) points at to the
    session's quarantine under the session branch name; the host fetches that
    ref into the target repo's ``refs/hypergolic/<scope>/<branch>``. HEAD, not
    a branch name, so the agent may branch freely in its checkout. Forced on
    both hops — session branches move non-fast-forward (amends, post-land
    resets), and both namespaces are ours."""
    await running_container(session, project)
    await exec_repo_git(
        session, project,
        f"git -C {slot.workdir} push --quiet origin "
        f"+{src}:{checkpoint_ref(slot.session_branch)}",
    )
    ref = hypergolic_ref(slot.ref_scope, slot.session_branch)
    result = await fetch_quarantine_ref(
        host_repo=slot.host_repo,
        session_id=session.id,
        repo=slot.repo,
        src_ref=checkpoint_ref(slot.session_branch),
        dst_ref=ref,
    )
    if result.returncode != 0:
        raise SandboxGitError(
            f"Could not fetch the session branch from the quarantine:\n"
            f"{result.stderr.strip()}"
        )
    return ref


async def fetch_child_ref(
    parent_session: Session, child_branch: str, repo_path: Path,
) -> str | None:
    """Revision naming a concluded child's tip inside the parent's repo, or None.

    A parent can't see the child's branch directly: concluded children
    survive only as ``refs/hypergolic/...`` on the host repo, which the
    parent's clone reads through ``origin`` — fetch the ref in (same name),
    then diff/merge against it.
    """
    ref = hypergolic_ref(parent_session.project_id, child_branch)
    fetch = await async_run_git_command(
        "fetch", "--quiet", "origin", f"+{ref}:{ref}", cwd=repo_path,
    )
    return ref if fetch.returncode == 0 else None


async def base_ref_for(session: Session, project: Project) -> str:
    """Host-repo ref naming the session's base: a real branch when the base
    is host-level, else the ``refs/hypergolic`` ref recorded when the child
    was provisioned off its parent's tip."""
    assert session.base_branch
    base = session.base_branch
    for candidate in (f"refs/heads/{base}", hypergolic_ref(project.id, base)):
        probe = await async_run_git_command(
            "rev-parse", "--verify", "--quiet", candidate, cwd=Path(project.path),
        )
        if probe.returncode == 0:
            return candidate
    raise SandboxGitError(
        f"Base `{base}` resolves to nothing in the host repo (neither a "
        "branch nor a preserved refs/hypergolic ref)."
    )


async def reconcile_after_land(
    session: Session, project: Project, slot: RepoSlot, landed_sha: str,
) -> bool:
    """Move the container checkout onto the freshly landed base tip.

    Only when the worktree is clean and HEAD is the commit that just landed —
    a dirty tree or a checkout elsewhere (agent pushed `other:<base>`) is the
    agent's business; git-native recovery (`git pull origin <base>`) works from
    either. Returns whether the checkout was moved.
    """
    script = (
        f"cd {slot.workdir} || exit 9\n"
        "git fetch --quiet origin || exit 9\n"
        'st=$(git status --porcelain) || exit 9\n'
        'head=$(git rev-parse HEAD) || exit 9\n'
        f'if [ -z "$st" ] && [ "$head" = "{landed_sha}" ]; then\n'
        f"  git reset --quiet --hard origin/{slot.base_branch} && echo moved\n"
        "fi\ntrue"
    )
    try:
        out = await exec_repo_git(session, project, script)
    except SandboxGitError as exc:
        logger.warning("post-land reconcile failed for %s: %s", slot.repo, exc)
        return False
    return "moved" in out
