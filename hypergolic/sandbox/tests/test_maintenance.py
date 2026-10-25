import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.enums import SessionStatus
from hypergolic.sandbox.manager import reap, sandbox_rows
from hypergolic.sandbox.manager.maintenance import prebuild_project_images
from hypergolic.sandbox.manager.reap import (
    bind_server_loop,
    reap_orphaned_compose_projects,
    schedule_reap,
)
from hypergolic.sandbox.manager.types import ExecResult
from hypergolic.sandbox.model.containers import Container, Image
from hypergolic.sandbox.model.sandbox import ProjectSandbox
from hypergolic.sandbox.tool import write_compose
from hypergolic.sessions import session_rows
from tests.conftest import make_project, make_session

@pytest.fixture(autouse=True)
def _authoritative_db():
    with patch.object(reap, "_has_authoritative_db", return_value=True):
        yield


async def _sandbox_row(session_id: str, compose_project: str, tool_id: str = "cmd", **fields) -> None:
    await sandbox_rows.create(session_id, tool_id, **{
        "status": "stopped", "config_path": "/fake/sandbox.yaml", **fields, "compose_project": compose_project,
    })


def _end_as(session_id: str, status: SessionStatus, *, stamp: bool = False) -> None:
    session_rows.update(session_id, status=status.value, concluded_at=datetime.now(UTC) if stamp else None)


def _docker_mock(managed: list[str]) -> AsyncMock:
    ps = ExecResult(stdout="\n".join(managed) + "\n", stderr="", returncode=0)
    ok = ExecResult(stdout="", stderr="", returncode=0)

    async def _run(*args, **kwargs):
        return ps if args[0] == "ps" else ok

    return AsyncMock(side_effect=_run)


def _down_projects(mock: AsyncMock) -> list[str]:
    return [
        call.args[2]
        for call in mock.await_args_list
        if call.args[0] == "compose" and "down" in call.args
    ]


@pytest.mark.db
async def test_reaps_concluded_and_unknown_projects_only():
    make_project("p1")
    live = make_session(project_id="p1")
    concluded = make_session(project_id="p1")
    _end_as(concluded, SessionStatus.CONCLUDED)

    stale = datetime.now(UTC) - timedelta(hours=2)
    await _sandbox_row(live, "hgcmdlive")
    await _sandbox_row(concluded, "hgcmdconcluded", updated_at=stale)

    docker = _docker_mock(["hgcmdlive", "hgcmdconcluded", "hgcmdorphan"])
    with (
        patch("hypergolic.sandbox.manager.docker._run_docker", docker),
        patch("hypergolic.sandbox.manager.reap.remove_gitdir_volume", AsyncMock()) as vols,
    ):
        reaped = await reap_orphaned_compose_projects()

    assert reaped == 2
    assert sorted(_down_projects(docker)) == ["hgcmdconcluded", "hgcmdorphan"]
    assert sorted(c.args[0] for c in vols.await_args_list) == ["hgcmdconcluded", "hgcmdorphan"]
    row = await sandbox_rows.get(concluded, "cmd")
    assert row is not None and row.status == "stopped"


@pytest.mark.db
async def test_reaps_errored_and_interrupted_children():
    make_project("p1")
    errored = make_session(project_id="p1")
    interrupted = make_session(project_id="p1")
    live_error = make_session(project_id="p1")
    _end_as(errored, SessionStatus.ERROR, stamp=True)
    _end_as(interrupted, SessionStatus.INTERRUPTED, stamp=False)
    _end_as(live_error, SessionStatus.ERROR, stamp=False)

    stale = datetime.now(UTC) - timedelta(hours=2)
    await _sandbox_row(errored, "hgcmderrored", updated_at=stale)
    await _sandbox_row(interrupted, "hgcmdinterrupted", updated_at=stale)
    await _sandbox_row(live_error, "hgcmdliveerror", updated_at=stale)

    docker = _docker_mock(["hgcmderrored", "hgcmdinterrupted", "hgcmdliveerror"])
    with (
        patch("hypergolic.sandbox.manager.docker._run_docker", docker),
        patch("hypergolic.sandbox.manager.reap.remove_gitdir_volume", AsyncMock()),
    ):
        assert await reap_orphaned_compose_projects() == 2

    assert sorted(_down_projects(docker)) == ["hgcmderrored", "hgcmdinterrupted"]


@pytest.mark.db
async def test_recently_touched_sandbox_survives_a_concluded_session():
    make_project("p1")
    concluded = make_session(project_id="p1")
    _end_as(concluded, SessionStatus.CONCLUDED)
    await _sandbox_row(concluded, "hgcmdfresh")

    docker = _docker_mock(["hgcmdfresh"])
    with patch("hypergolic.sandbox.manager.docker._run_docker", docker):
        assert await reap_orphaned_compose_projects() == 0

    assert _down_projects(docker) == []


async def test_reap_survives_docker_being_unavailable():
    docker = AsyncMock(side_effect=OSError("no docker"))
    with patch("hypergolic.sandbox.manager.docker._run_docker", docker):
        assert await reap_orphaned_compose_projects() == 0


async def test_prebuild_skips_sandboxes_with_no_dockerfile(tmp_path):
    pulled = ProjectSandbox(
        id="pulled",
        containers=[Container(id="dev", image="ubuntu", skip_workspace_mount=True)],
    )
    built = ProjectSandbox(
        id="built", containers=[Container(id="dev", image=Image(base="x"))]
    )

    docker = AsyncMock(return_value=ExecResult(stdout="", stderr="", returncode=0))
    with (
        patch("hypergolic.sandbox.manager.docker._run_docker", docker),
        patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path),
    ):

        write_compose(pulled)
        write_compose(built)
        await prebuild_project_images([pulled, built])

    build_configs = [
        call.args[call.args.index("-f") + 1]
        for call in docker.await_args_list
        if "build" in call.args
    ]
    assert len(build_configs) == 1
    assert build_configs[0].endswith("built.compose.yaml")


async def test_schedule_reap_is_debounced_and_single_flight():
    reap_fn = AsyncMock(return_value=0)
    bind_server_loop(asyncio.get_running_loop())
    try:
        with patch.object(reap, "reap_orphans", reap_fn):
            schedule_reap()
            schedule_reap()
            await asyncio.sleep(0.05)
    finally:
        bind_server_loop(None)
        reap._last_reap_at = 0.0

    assert reap_fn.await_count == 1


def test_schedule_reap_without_a_server_loop_does_nothing():
    reap_fn = AsyncMock()
    with patch.object(reap, "reap_orphans", reap_fn):
        schedule_reap()
    assert reap_fn.await_count == 0


async def test_reap_refuses_to_act_on_an_ephemeral_db():
    docker = _docker_mock(["hgcmdsomeoneslivestack"])
    with (
        patch.object(reap, "_has_authoritative_db", return_value=False),
        patch("hypergolic.sandbox.manager.docker._run_docker", docker),
    ):
        assert await reap_orphaned_compose_projects() == 0
    assert docker.await_count == 0


async def test_converge_running_workspaces_targets_live_cmd_sandboxes():
    from hypergolic.sandbox.manager.maintenance import converge_running_workspaces

    make_project("p-conv")
    live = make_session(project_id="p-conv")
    ended = make_session(project_id="p-conv")
    _end_as(ended, SessionStatus.CONCLUDED)

    for session_id, tool_id in [(live, "cmd"), (live, "other-tool"), (ended, "cmd")]:
        await _sandbox_row(session_id, f"hg-{tool_id}-x", tool_id, status="running")

    with patch(
        "hypergolic.sandbox.manager.converge.converge_workspace_repos", AsyncMock(),
    ) as hook:
        await converge_running_workspaces()

    hook.assert_awaited_once_with(live, "cmd")
