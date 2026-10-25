from unittest.mock import AsyncMock, patch

from hypergolic.sandbox.manager.converge import converge_workspace_repos, ensure_up
from hypergolic.sandbox.manager import sandbox_rows

from .conftest import make_sandbox_row, patch_docker

PROVISION = "hypergolic.sandbox.manager.repo_provision.provision_sandbox"
HOOK = "hypergolic.sandbox.manager.converge.converge_workspace_repos"


async def test_ensure_up_converges_workspace_repos(sid, cfg):
    row = await make_sandbox_row(sid, tool_id="cmd")
    with patch_docker(), patch(HOOK, AsyncMock()) as hook:
        await ensure_up(
            session_id=sid, sid="cmd", row_id=row.id,
            compose_project="hg-cmd-x", canonical_path=cfg, run_path=cfg,
            targets={}, external_volumes=[], project_root="/wt", build=False,
        )
    hook.assert_awaited_once_with(sid, "cmd")
    refreshed = await sandbox_rows.get(sid, "cmd")
    assert refreshed is not None and refreshed.status == "running"


async def test_hook_skips_non_workspace_sandboxes(sid):
    with patch(PROVISION, AsyncMock()) as provision:
        await converge_workspace_repos(sid, "my-tool")
    provision.assert_not_awaited()


async def test_hook_converges_ready_workspace_session(sid):
    with patch(PROVISION, AsyncMock()) as provision:
        await converge_workspace_repos(sid, "cmd")
    provision.assert_awaited_once()


async def test_hook_leaves_provisioning_sessions_to_creation_path():
    from tests.conftest import make_project, make_session

    make_project("p-prov")
    sid = make_session(project_id="p-prov", worktree_status="cloning")
    with patch(PROVISION, AsyncMock()) as provision:
        await converge_workspace_repos(sid, "cmd")
    provision.assert_not_awaited()

