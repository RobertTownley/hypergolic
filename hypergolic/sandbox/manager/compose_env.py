import asyncio
from pathlib import Path


import hypergolic.config.settings as config
from hypergolic.sessions import session_rows
from hypergolic.commands.materialize import tools_dir
from hypergolic.git.eval_source import ensure_eval_source
from hypergolic.git.harness_repo import harness_workspace_path
from hypergolic.git.quarantine import ensure_quarantine
from hypergolic.git.sandbox_repo import REPO_APP, REPO_HARNESS, REPO_SHARED
from hypergolic.harness.app.state import get_app
from hypergolic.sandbox.model.constants import (
    HARNESS_ENV,
    HOST_OBJECTS_APP_ENV,
    HOST_REPO_APP_ENV,
    HOST_REPO_HARNESS_ENV,
    HOST_REPO_SHARED_ENV,
    PACKAGE_ENV,
    QUARANTINE_APP_ENV,
    QUARANTINE_HARNESS_ENV,
    QUARANTINE_SHARED_ENV,
    SESSION_ENV,
    SHARED_ENV,
    TOOLS_ENV,
)
from hypergolic.sandbox.shared import ensure_shared_dir, session_shared_workspace

def settings_harness_gitdir() -> Path | None:
    gitdir = config.HARNESS_DIR / ".git"
    return gitdir if gitdir.is_dir() else None


async def compose_env(session_id: str, project_root: str) -> dict[str, str]:
    tools = tools_dir(session_id)
    tools.mkdir(parents=True, exist_ok=True)
    harness: Path | None = None
    if settings_harness_gitdir() is not None:
        harness = harness_workspace_path(session_id)
        harness.mkdir(parents=True, exist_ok=True)
    env = {
        "HYPERGOLIC_WORKSPACE": project_root,
        HARNESS_ENV: str(harness) if harness else "/dev/null",
        TOOLS_ENV: str(tools),
        PACKAGE_ENV: str(Path(__file__).resolve().parent.parent.parent),
        SESSION_ENV: session_id,
    }
    row = await session_rows.afetch(session_id)
    project_id, conducted_by = (row.project_id, row.conducted_by) if row else (None, None)

    def _quarantine(env_key: str, repo: str, gitdir: Path) -> None:
        env[env_key] = str(ensure_quarantine(
            session_id=session_id, repo=repo, host_gitdir=gitdir,
        ))

    if project_id:
        shared_repo = await asyncio.to_thread(ensure_shared_dir, project_id)
        shared_ws = session_shared_workspace(session_id)
        shared_ws.mkdir(parents=True, exist_ok=True)
        env[SHARED_ENV] = str(shared_ws)
        env[HOST_REPO_SHARED_ENV] = str(shared_repo / ".git")
        await asyncio.to_thread(
            _quarantine, QUARANTINE_SHARED_ENV, REPO_SHARED, shared_repo / ".git",
        )
        project = get_app().find_project(project_id)
        if project is not None:
            host_gitdir = Path(project.path) / ".git"
            if host_gitdir.exists():
                env[HOST_REPO_APP_ENV] = str(host_gitdir)
                if conducted_by is not None:
                    source = await asyncio.to_thread(
                        ensure_eval_source, session_id, host_gitdir,
                    )
                    env[HOST_REPO_APP_ENV] = str(source)
                    env[HOST_OBJECTS_APP_ENV] = str(host_gitdir / "objects")
                await asyncio.to_thread(
                    _quarantine, QUARANTINE_APP_ENV, REPO_APP, host_gitdir,
                )
    harness_gitdir = settings_harness_gitdir()
    if harness_gitdir is not None:
        env[HOST_REPO_HARNESS_ENV] = str(harness_gitdir)
        await asyncio.to_thread(
            _quarantine, QUARANTINE_HARNESS_ENV, REPO_HARNESS, harness_gitdir,
        )
    return env
