from hypergolic.git.commands import run_git_command
from hypergolic.git.sandbox_repo import container_name
from hypergolic.harness.project import Project
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sandbox.manager.repo_report import RepoProvisionError
from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID

def host_git_identity() -> tuple[str, str]:
    name = run_git_command("config", "--get", "user.name").stdout.strip()
    email = run_git_command("config", "--get", "user.email").stdout.strip()
    return name or "Hypergolic", email or "agent@hypergolic.local"


def workspace_service(project: Project) -> str:
    sandbox = project.resolved_sandbox
    assert sandbox is not None
    service = next(
        (c.id for c in sandbox.containers if not c.skip_workspace_mount), None,
    )
    if service is None:
        raise RepoProvisionError(
            "No container in this sandbox mounts the workspace; cannot clone."
        )
    return service


async def session_container(session_id: str, project: Project) -> str | None:
    sandbox = await sandbox_rows.get(session_id, SANDBOX_TOOL_ID)
    if sandbox is None or sandbox.status != "running" or not sandbox.compose_project:
        return None
    return container_name(sandbox.compose_project, workspace_service(project))
