from __future__ import annotations

import shlex
import shutil
from pathlib import Path

from hypergolic.git.commands import async_run_git_command
from hypergolic.harness.app.state import get_app
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.harness.primitives.validation import ValidationResult
from hypergolic.schemas import Session

NO_GH = "The GitHub CLI (`gh`) is not installed on the host. Tell the user instead of retrying."


async def _git_ok(cwd: Path, *args: str) -> bool:
    return (await async_run_git_command(*args, cwd=cwd)).returncode == 0


def _resolve_body(inp, session) -> str | None:
    if not inp.body_file:
        return None
    path = inp.body_file
    if path.startswith("/app/"):
        path = str(Path(session.worktree_path) / path[len("/app/"):])
    try:
        inp.body = Path(path).read_text()
    except OSError as exc:
        return f"Could not read --body-file: {exc}"
    return None


def _land_first(branch: str) -> str:
    return (
        f"Your sandbox HEAD has work `{branch}` lacks on the user's machine. Land it first "
        f"(`git push origin HEAD:{branch}`), then publish."
    )


def _diverged(branch: str) -> str:
    return (
        f"Your sandbox HEAD and the user's `{branch}` have diverged. Bring theirs in "
        f"(`git fetch origin {branch} && git rebase FETCH_HEAD`), land "
        f"(`git push origin HEAD:{branch}`), then publish."
    )


async def _fast_forward(session: Session, project, workdir: str, branch: str) -> None:
    from hypergolic.git.sandbox_integrate import exec_repo_git

    ref = shlex.quote(f"refs/heads/{branch}")
    await exec_repo_git(
        session, project,
        f"git -C {workdir} fetch --quiet origin {ref} && git -C {workdir} merge --ff-only --quiet FETCH_HEAD",
    )


async def _dirty(session: Session, project, workdir: str) -> bool:
    from hypergolic.git.sandbox_integrate import SandboxGitError, exec_repo_git

    try:
        return bool((await exec_repo_git(session, project, f"git -C {workdir} status --porcelain")).strip())
    except SandboxGitError:
        return False


async def _problem(inp, ctx: ToolContext, notes: list[str]) -> str | None:
    from hypergolic.git.sandbox_integrate import SandboxGitError, app_slot, refresh_session_ref

    if shutil.which("gh") is None:
        return NO_GH
    if inp.action != "publish":
        return None
    if err := _resolve_body(inp, ctx.session):
        return err
    branch = inp.branch
    if not branch:
        return "publish needs a branch."
    session = ctx.session
    project = get_app().find_project(session.project_id)
    if project is None:
        return f"Unknown project {session.project_id!r}."
    cwd = Path(session.project_path)
    target = f"refs/heads/{branch}"
    if not await _git_ok(cwd, "rev-parse", "--verify", "--quiet", target):
        return (
            f"`{branch}` is not a branch on the user's machine. Land onto it first: "
            f"`git push origin HEAD:{branch}`."
        )
    try:
        head = await refresh_session_ref(session, project)
    except SandboxGitError as exc:
        return str(exc)
    workdir = app_slot(session, project).workdir
    if not await _git_ok(cwd, "diff", "--quiet", head, target):
        if await _git_ok(cwd, "merge-base", "--is-ancestor", target, head):
            return _land_first(branch)
        if not await _git_ok(cwd, "merge-base", "--is-ancestor", head, target):
            return _diverged(branch)
        try:
            await _fast_forward(session, project, workdir, branch)
        except SandboxGitError as exc:
            return (
                f"The user's `{branch}` is ahead of your sandbox, and the fast-forward failed:\n"
                f"{exc}\nCommit or stash the overlapping changes, then publish again."
            )
        notes.append(
            f"Sandbox fast-forwarded to the user's `{branch}`; `git log -p ORIG_HEAD..HEAD` shows what came in."
        )
    if await _dirty(session, project, workdir):
        notes.append("Your sandbox has uncommitted changes; they are not in this PR.")
    return None


async def align(inp, ctx: ToolContext) -> ValidationResult:
    notes: list[str] = []
    if problem := await _problem(inp, ctx, notes):
        return ValidationResult.invalid(problem)
    return ValidationResult.valid("\n".join(notes) or None)
