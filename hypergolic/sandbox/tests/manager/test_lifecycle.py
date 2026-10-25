from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sessions import session_rows
from hypergolic.sandbox.manager.lifecycle import cleanup_session_sandboxes, reconcile_sandbox_rows, stop_sandbox
from hypergolic.sandbox.manager.types import ExecResult

from .conftest import make_sandbox_row, patch_docker


LIFECYCLE = "hypergolic.sandbox.manager.lifecycle"


async def test_stop_noops(sid):
    await stop_sandbox(sid, "nonexistent")
    await make_sandbox_row(sid, status="stopped")
    with patch("hypergolic.sandbox.manager.docker._run_docker") as mock:
        await stop_sandbox(sid, "my-tool")
    mock.assert_not_called()


async def test_stop_running(sid, cfg):
    await make_sandbox_row(sid, config_path=cfg, compose_project="hg-my_tool-abc")
    with patch_docker():
        await stop_sandbox(sid, "my-tool")
    sandbox = await sandbox_rows.get(sid, "my-tool")
    assert sandbox is not None and sandbox.status == "stopped"


@pytest.mark.parametrize("docker_mock", [
    AsyncMock(return_value=ExecResult(stdout="", stderr="Error", returncode=1)),
    AsyncMock(side_effect=Exception("boom")),
])
async def test_stop_down_failure_still_marks_stopped(sid, cfg, docker_mock):
    await make_sandbox_row(sid, config_path=cfg, compose_project="hg-my_tool-abc")
    with patch_docker(side_effect=docker_mock):
        await stop_sandbox(sid, "my-tool")
    sandbox = await sandbox_rows.get(sid, "my-tool")
    assert sandbox is not None and sandbox.status == "stopped"


async def test_cleanup_session_sandboxes(sid, cfg):
    await make_sandbox_row(sid, tool_id="t1", config_path=cfg, compose_project="hg-t1-abc")
    await make_sandbox_row(sid, tool_id="t2", status="pending", config_path=cfg, compose_project="hg-t2-abc")
    with patch_docker():
        await cleanup_session_sandboxes(sid)
    for tool in ("t1", "t2"):
        row = await sandbox_rows.get(sid, tool)
        assert row is not None and row.status == "stopped"


async def test_reconcile_marks_containerless_rows_stopped(sid, cfg):
    await make_sandbox_row(sid, tool_id="gone", config_path=cfg, compose_project="hg-gone-abc")
    ps = ExecResult(stdout="some-other-project\n", stderr="", returncode=0)
    with patch_docker(side_effect=AsyncMock(return_value=ps)):
        await reconcile_sandbox_rows()
    row = await sandbox_rows.get(sid, "gone")
    assert row is not None and row.status == "stopped"


async def test_reconcile_leaves_surviving_stacks_running(sid, cfg):
    await make_sandbox_row(sid, tool_id="alive", config_path=cfg, compose_project="hg-alive-abc")
    ps = ExecResult(stdout="hg-alive-abc\n", stderr="", returncode=0)
    mock_docker = AsyncMock(return_value=ps)
    with patch_docker(side_effect=mock_docker):
        await reconcile_sandbox_rows()
    row = await sandbox_rows.get(sid, "alive")
    assert row is not None and row.status == "running"
    assert mock_docker.call_count == 1


async def test_reconcile_reaps_gitdir_volumes_of_dead_ended_sessions(sid, cfg):
    await make_sandbox_row(sid, tool_id="gone", config_path=cfg, compose_project="hg-gone-abc")
    session_rows.update(sid, status="concluded")
    ps = ExecResult(stdout="", stderr="", returncode=0)
    with (
        patch_docker(side_effect=AsyncMock(return_value=ps)),
        patch(f"{LIFECYCLE}.remove_session_gitdir_volumes", AsyncMock()) as vols,
    ):
        await reconcile_sandbox_rows()
    vols.assert_awaited_once_with(sid)


async def test_reconcile_tolerates_docker_down(sid, cfg):
    await make_sandbox_row(sid, tool_id="t", config_path=cfg, compose_project="hg-t-abc")
    with patch_docker(side_effect=AsyncMock(side_effect=OSError("no docker"))):
        await reconcile_sandbox_rows()
    row = await sandbox_rows.get(sid, "t")
    assert row is not None and row.status == "running"
