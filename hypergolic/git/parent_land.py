"""Landing a child's app work into its parent's sandbox branch.

A dispatched child branches off its parent's *session* branch, which exists
only in the parent's sandbox (the host sees it as a checkpoint ref). So a
child's ``git push origin HEAD:<base>`` cannot advance a host branch: the land
pipeline checkpoints the parent's current tip, builds and gates the candidate
host-side as usual, then fast-forwards the parent's checkout *inside the
parent's container*. No ``refs/heads`` branch moves on the host.

The child's checkout is named after the parent's own base (``main``), so it
pushes the words it would push in a top-level session; :func:`land_parent`
maps that name (or the real parent branch name) back to the parent.

A child with an app pin roots at a *pin branch in the parent's sandbox*
(:func:`create_parent_pin`) rather than at the parent's live branch. Its lands
advance that branch in the parent's repo (never checked out, so no working
tree is touched) — again, no host ``refs/heads`` branch moves.
"""

from __future__ import annotations

import secrets
import shlex
from dataclasses import dataclass, replace

from hypergolic.git.commands import async_run_git_command
from hypergolic.git.sandbox_integrate import SandboxGitError, app_slot, exec_repo_git, refresh_slot_ref
from hypergolic.harness.project import Project
from hypergolic.schemas import Session


def _load(session_id: str) -> Session | None:
    from hypergolic.sessions.operations import load_session  # cycle

    try:
        return load_session(session_id)
    except Exception:
        return None


#: Branch-name prefix of pin branches made in a parent's sandbox.
PARENT_PIN_PREFIX = "pin/"


@dataclass(frozen=True)
class ParentBranch:
    """The parent-sandbox branch a child lands into."""

    parent: Session
    branch: str   # branch name in the parent's /app repo
    live: bool    # True: the parent's checked-out session branch; False: a pin branch


def parent_pin_name(sha: str) -> str:
    """A fresh pin-branch name; unique per child so siblings never share one."""
    return f"{PARENT_PIN_PREFIX}{sha[:12]}-{secrets.token_hex(3)}"


async def create_parent_pin(parent: Session, project: Project, *, sha: str, name: str) -> None:
    """Create branch *name* at *sha* in the parent's /app repo (not checked out).

    The sha's objects are visible there: the clone alternates into the host
    object store. Raises SandboxGitError when the parent sandbox can't do it.
    """
    out = await exec_repo_git(
        parent, project,
        f"git -C /app branch --no-track {shlex.quote(name)} {shlex.quote(sha)} && echo CREATED",
    )
    if "CREATED" not in out:
        raise SandboxGitError(f"could not create `{name}` at `{sha[:12]}` in the parent's sandbox")


async def drop_parent_pin(parent: Session, project: Project, *, name: str, sha: str) -> bool:
    """Delete pin branch *name* from the parent's /app only while it still
    points at *sha*: a pin nothing landed on. A pin with landed work stays for
    the parent to read. Never raises."""
    ref = shlex.quote(f"refs/heads/{name}")
    try:
        out = await exec_repo_git(
            parent, project, f"git -C /app update-ref -d {ref} {shlex.quote(sha)} 2>/dev/null && echo DROPPED",
        )
    except Exception:
        return False
    return "DROPPED" in out


def parent_of(session: Session) -> ParentBranch | None:
    """The parent-sandbox branch *session* branches off, else None
    (top-level sessions, and children rooted at a host branch)."""
    if not session.parent_id or not session.base_branch:
        return None
    parent = _load(session.parent_id)
    if parent is None:
        return None
    if parent.worktree_branch == session.base_branch:
        return ParentBranch(parent, session.base_branch, live=True)
    if session.base_branch.startswith(PARENT_PIN_PREFIX):
        return ParentBranch(parent, session.base_branch, live=False)
    return None


def visible_base(session: Session) -> str | None:
    """The base name the session sees and pushes to: the parent's own base
    for a child of a parent-sandbox branch, else the session's base."""
    pb = parent_of(session)
    if pb is not None and pb.parent.base_branch:
        return pb.parent.base_branch
    return session.base_branch


def land_parent(session: Session, branch: str) -> ParentBranch | None:
    """The parent branch to land into when *branch* names this child's base,
    or names any branch from a conducted (--eval) child: a sim never moves a
    host branch."""
    from hypergolic.tools.eval_conduct import is_conducted

    pb = parent_of(session)
    if pb is None:
        return None
    if is_conducted(session):
        return pb
    return pb if branch in {pb.branch, pb.parent.base_branch} else None


async def parent_tip(pb: ParentBranch, project: Project) -> str:
    """Checkpoint the parent's branch host-side; its sha."""
    slot = app_slot(pb.parent, project)
    if pb.live:
        ref = await refresh_slot_ref(pb.parent, project, slot)
    else:
        slot = replace(slot, session_branch=pb.branch)
        ref = await refresh_slot_ref(pb.parent, project, slot, src=f"refs/heads/{pb.branch}")
    rev = await async_run_git_command(
        "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=slot.host_repo,
    )
    if rev.returncode != 0:
        raise SandboxGitError(f"parent checkpoint `{ref}` does not resolve")
    return rev.stdout.strip()


def _advance_live_script(old: str, new: str) -> str:
    # A dirty tree merges when git can do so without overwriting local edits,
    # and refuses otherwise — the same rule as a dirty host checkout.
    return (
        "cd /app || exit 9\n"
        "head=$(git rev-parse HEAD) || exit 9\n"
        f'[ "$head" = {old} ] || {{ echo "STALE $head"; exit 0; }}\n'
        f"if out=$(git merge --ff-only --quiet {new} 2>&1); then echo MERGED; "
        'else printf "REFUSED %s\\n" "$out"; fi'
    )


def _advance_pin_script(ref: str, old: str, new: str) -> str:
    # Not checked out: a compare-and-swap ref update, fast-forward only.
    return (
        "cd /app || exit 9\n"
        f"cur=$(git rev-parse {ref}) || exit 9\n"
        f'[ "$cur" = {old} ] || {{ echo "STALE $cur"; exit 0; }}\n'
        f"git merge-base --is-ancestor {old} {new} || {{ echo NOTFF; exit 0; }}\n"
        f"git update-ref {ref} {new} {old} && echo MERGED"
    )


async def advance_parent(
    pb: ParentBranch, project: Project, *, old_sha: str, new_commit: str,
) -> tuple[bool, str]:
    """Fast-forward the parent's branch from *old_sha* to *new_commit*.

    Runs in the parent's container. The candidate's objects are already
    visible there (the clone alternates into the host object store).
    """
    old, new = shlex.quote(old_sha), shlex.quote(new_commit)
    script = (
        _advance_live_script(old, new) if pb.live
        else _advance_pin_script(shlex.quote(f"refs/heads/{pb.branch}"), old, new)
    )
    try:
        out = (await exec_repo_git(pb.parent, project, script)).strip()
    except SandboxGitError as exc:
        return False, f"could not reach the parent session's sandbox: {exc}"
    if out.startswith("MERGED"):
        return True, new_commit
    if out.startswith("STALE"):
        return False, "the parent's branch moved while gates ran"
    if out.startswith("NOTFF"):
        return False, "the candidate does not fast-forward the parent's branch"
    return False, (
        "the parent session has uncommitted changes that this merge would "
        f"overwrite:\n{out.removeprefix('REFUSED').strip()}"
    )


async def reset_child_onto(
    session: Session, project: Project, *, pushed_sha: str, new_tip: str, branch: str,
) -> bool:
    """Point the child's ``origin/<branch>`` at *new_tip*, and move its clean
    checkout (still at *pushed_sha*) onto it."""
    tip = shlex.quote(new_tip)
    tracking = shlex.quote(f"refs/remotes/origin/{branch}")
    script = (
        "cd /app || exit 9\n"
        f"git update-ref {tracking} {tip} || true\n"
        "st=$(git status --porcelain) || exit 9\n"
        "head=$(git rev-parse HEAD) || exit 9\n"
        f'if [ -z "$st" ] && [ "$head" = {shlex.quote(pushed_sha)} ]; then\n'
        f"  git reset --quiet --hard {tip} && echo moved\n"
        "fi\ntrue"
    )
    try:
        return "moved" in await exec_repo_git(session, project, script)
    except SandboxGitError:
        return False
