import asyncio
import subprocess
from pathlib import Path


class GitCommandError(Exception):
    def __init__(
        self, command: str, returncode: int, stderr: str, stdout: str = "",
    ):
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        super().__init__(f"git {command} failed (exit {returncode}): {stderr}")


class GitResult:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def git_repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def merge_base(repo: Path, base_branch: str) -> str | None:
    result = run_git_command("merge-base", base_branch, "HEAD", cwd=repo)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def unmerged_commit_count(repo: Path, base: str, branch: str) -> int:
    result = run_git_command(
        "rev-list", "--count", "--cherry-pick", "--right-only", "--no-merges",
        f"{base}...{branch}", cwd=repo,
    )
    try:
        return int((result.stdout or "0").strip() or 0)
    except ValueError:
        return 0


def run_git_command(
    *args: str, cwd: Path | None = None, check: bool = False,
) -> subprocess.CompletedProcess[str]:
    from hypergolic.git.container_git import routes_to_sandbox, run_container_git

    repo = cwd or git_repo_root()
    if routes_to_sandbox(cwd):
        result = run_container_git(repo, *args)
    else:
        result = subprocess.run(
            ["git", *args],
            capture_output=True, text=True, cwd=repo,
        )
    if check and result.returncode != 0:
        raise GitCommandError(
            command=args[0] if args else "unknown",
            returncode=result.returncode,
            stderr=result.stderr.strip(),
            stdout=result.stdout.strip(),
        )
    return result


async def async_run_git_command(
    *args: str, cwd: Path | None = None, check: bool = False,
) -> GitResult:
    from hypergolic.git.container_git import (
        async_run_container_git,
        routes_to_sandbox,
    )

    repo = cwd or await asyncio.to_thread(git_repo_root)
    if routes_to_sandbox(cwd):
        result = await async_run_container_git(repo, *args)
        returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
    else:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo,
        )
        raw_stdout, raw_stderr = await proc.communicate()
        returncode = proc.returncode or 0
        stdout = raw_stdout.decode(errors="replace")
        stderr = raw_stderr.decode(errors="replace")
    if check and returncode != 0:
        raise GitCommandError(
            command=args[0] if args else "unknown",
            returncode=returncode,
            stderr=stderr.strip(),
            stdout=stdout.strip(),
        )
    return GitResult(returncode=returncode, stdout=stdout, stderr=stderr)


async def git_checked(
    cwd: Path, *args: str, error: type[Exception] = RuntimeError,
) -> str:
    result = await async_run_git_command(*args, cwd=cwd)
    if result.returncode != 0:
        raise error(
            f"git {args[0]} failed:\n{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout
