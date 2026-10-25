import asyncio
import logging
from pathlib import Path

from hypergolic.dispatch.conclude.errors import BranchPreservationError
from hypergolic.git.commands import async_run_git_command
from hypergolic.git.sandbox_integrate import (
    SandboxGitError,
    base_ref_for,
    refresh_session_ref,
)
from hypergolic.git.sandbox_repo import delete_hypergolic_ref
from hypergolic.git.worktree_lifecycle import schedule_teardown, TeardownKwargs
from hypergolic.harness.app.state import get_app
from hypergolic.sandbox.manager.workspace import session_container
from hypergolic.schemas import Session
from hypergolic.sessions.operations import clear_session_worktree_fields

logger = logging.getLogger(__name__)

def _project_for(session: Session):
    try:
        return get_app().find_project(session.project_id)
    except RuntimeError:
        return None


async def teardown_worktree_at_conclude(
    session: Session,
    *,
    delete_worktree: bool = True,
    delete_branch_flag: bool = True,
) -> str | None:
    """Apply workspace teardown per the agent's conclude options.

    Returns the branch name that survives (for :class:`DispatchResult`), or
    ``None`` if the branch was dropped or there was no workspace to begin
    with. The branch itself lives in the sandbox's gitdir volume, which dies
    with the session — "surviving" means its tip was fetched to the host as
    ``refs/hypergolic/<project>/<branch>``.

    Conclude never starts the sandbox and never checks for uncommitted
    changes: work that lives only in the container is disposable (session
    history is the recovery path). Behavior by flag combo:

    - ``delete_worktree=True`` (default): the workspace dir is removed.
    - ``delete_worktree=False``: the workspace dir is left in place. The
      session's ``worktree_path`` DB column is still cleared so the UI no
      longer points the session at it. The dir is files-only — its gitdir
      dies with the sandbox.
    - ``delete_branch_flag=False``: if the sandbox is running, the branch is
      fetched back and preserved *iff* it has commits beyond base. A stopped
      sandbox preserves nothing.
    - ``delete_branch_flag=True``: no fetch-back; any previously preserved
      ref is deleted.
    """
    worktree_path = session.worktree_path
    branch = session.worktree_branch
    base_branch = session.base_branch

    if not worktree_path or not branch or not base_branch:
        return branch

    wt = Path(worktree_path)
    if not wt.exists():
        return branch

    if delete_branch_flag:
        await asyncio.to_thread(
            delete_hypergolic_ref, session.project_path, session.project_id, branch,
        )
        branch_survives = False
    else:
        branch_survives = await preserve_sandbox_branch(session)

    # (1) clear DB fields synchronously so the UI immediately reflects the
    # concluded state, then (2) remove the workspace dir on a daemon thread
    # so the caller (the conclude tool) doesn't wait on filesystem I/O.
    if delete_worktree:
        teardown_kwargs: TeardownKwargs = dict(
            session_id=session.id, worktree_path=str(wt),
        )
        schedule_teardown(**teardown_kwargs)

    if not branch_survives:
        # Null the branch column now — a non-null ``worktree_branch`` means
        # "this branch still exists" (merge-candidate discovery keys on it).
        await asyncio.to_thread(
            clear_session_worktree_fields, session.id, clear_branch=True
        )
        return None

    await asyncio.to_thread(clear_session_worktree_fields, session.id)
    return branch


async def preserve_sandbox_branch(session: Session) -> bool:
    """Fetch the session branch to the host before teardown.

    The gitdir volume dies with the sandbox, so committed-but-unmerged work
    survives only as a ``refs/hypergolic/...`` ref on the host — which is
    also what ``merge_child``/``diff_child`` read. Returns True when the
    fetched branch has commits beyond base (i.e. there is something to
    preserve). Only a running sandbox is asked: conclude never starts (or
    rebuilds) one, so a stopped sandbox preserves nothing.
    """
    assert session.worktree_branch and session.base_branch
    project = _project_for(session)
    if project is None:
        return False  # unregistered project: nothing can be fetched
    if await session_container(session.id, project) is None:
        logger.info(
            "Sandbox of %s is not running at conclude; not preserving branch %s",
            session.id, session.worktree_branch,
        )
        return False
    try:
        ref = await refresh_session_ref(session, project)
        base_ref = await base_ref_for(session, project)
    except SandboxGitError as exc:
        raise BranchPreservationError(str(exc)) from exc
    result = await async_run_git_command(
        "rev-list", "--count", f"{base_ref}..{ref}",
        cwd=Path(session.project_path),
    )
    if result.returncode != 0:
        return True  # can't prove it's empty: preserve
    try:
        has_commits = int(result.stdout.strip() or "0") > 0
    except ValueError:
        return False
    if not has_commits:
        # Don't leave an empty ref littering refs/hypergolic.
        await async_run_git_command(
            "update-ref", "-d", ref, cwd=Path(session.project_path),
        )
    return has_commits
