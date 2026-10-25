from __future__ import annotations

from hypergolic.contrib.tools.land.inputs import LandRejected, Target
from hypergolic.gates.candidate import resolve_branch
from hypergolic.git.commands import async_run_git_command


async def _rev(host, ref: str) -> str | None:
    result = await async_run_git_command(
        "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=host,
    )
    return result.stdout.strip() if result.returncode == 0 else None


async def resolve_target(host, branch: str, root_branch: str, sha: str) -> Target:
    local = await resolve_branch(host, branch)
    if local is not None:
        return Target(local)
    remote = f"refs/remotes/origin/{branch}"
    remote_sha = await _rev(host, remote)
    if remote_sha is not None:
        return Target(remote_sha, create=True, upstream=f"origin/{branch}")
    root_sha = await resolve_branch(host, root_branch)
    if root_sha is None:
        raise LandRejected(
            f"`{branch}` does not exist and the session base `{root_branch}` "
            "is not a branch in the host repo"
        )
    fork = await async_run_git_command("merge-base", root_sha, sha, cwd=host)
    if fork.returncode != 0:
        raise LandRejected(
            f"`{branch}` does not exist and the pushed commits share no "
            f"history with `{root_branch}`"
        )
    return Target(fork.stdout.strip(), create=True)


async def create_branch(host, branch: str, target: Target) -> None:
    created = await async_run_git_command("branch", "--no-track", branch, target.sha, cwd=host)
    if created.returncode != 0:
        raise LandRejected(
            f"could not create `{branch}` at `{target.sha[:8]}`:\n"
            f"{created.stderr.strip() or created.stdout.strip()}"
        )
    if target.upstream:
        await async_run_git_command(
            "branch", f"--set-upstream-to={target.upstream}", branch, cwd=host,
        )
