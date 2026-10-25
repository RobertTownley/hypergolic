from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import hypergolic.config.settings as config
from hypergolic.git.commands import async_run_git_command, run_git_command


def eval_source_path(session_id: str) -> Path:
    return config.session_internals_dir(session_id) / "source" / "app.git"


def ensure_eval_source(session_id: str, host_gitdir: Path) -> Path:
    path = eval_source_path(session_id)
    if not (path / "HEAD").exists():
        path.mkdir(parents=True, exist_ok=True)
        run_git_command("init", "--quiet", "--bare", ".", cwd=path, check=True)
    (path / "objects" / "info" / "alternates").write_text(f"{host_gitdir}/objects\n")
    return path


async def seed_eval_source(
    session_id: str, host_repo: Path, branch: str, sha: str,
) -> None:
    path = eval_source_path(session_id)
    tags = await async_run_git_command(
        "for-each-ref", "--merged", sha, "--format=%(refname) %(objectname)",
        "refs/tags", cwd=host_repo, check=True,
    )
    updates = [f"update refs/heads/{branch} {sha}"]
    updates += [f"update {line}" for line in tags.stdout.splitlines() if line.strip()]
    await _update_refs(path, updates)
    await async_run_git_command(
        "symbolic-ref", "HEAD", f"refs/heads/{branch}", cwd=path, check=True,
    )


async def set_eval_branch(session_id: str, branch: str, sha: str) -> None:
    path = eval_source_path(session_id)
    if (path / "HEAD").exists():
        await _update_refs(path, [f"update refs/heads/{branch} {sha}"])


async def _update_refs(path: Path, updates: list[str]) -> None:
    def run() -> None:
        subprocess.run(
            ["git", "update-ref", "--stdin"], cwd=path, check=True,
            input="\n".join(updates) + "\n", text=True, capture_output=True,
        )

    await asyncio.to_thread(run)
