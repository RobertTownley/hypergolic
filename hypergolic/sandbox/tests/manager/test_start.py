import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sessions import session_rows
from hypergolic.sandbox.manager.provisioning import _config_hash
from hypergolic.sandbox.manager.start import start_sandbox
from hypergolic.sandbox.manager.types import ExecResult, SandboxError
from hypergolic.sandbox.manager.converge import BUILD_TIMEOUT_SECONDS
from hypergolic.sandbox.manager.start import _detached_tasks

from .conftest import COMPOSE, OK, make_sandbox_row, patch_docker


async def test_already_running_returns_existing_project(sid, cfg):
    await make_sandbox_row(sid, tool_id="t1", compose_project="existing-project",
                     config_hash=_config_hash(cfg))
    with patch_docker() as run:
        assert await start_sandbox(sid, "t1", cfg, "/workspace") == "existing-project"
    assert all(c.args == ("info",) for c in run.call_args_list)


async def test_config_drift_reconverges_running_sandbox(sid, cfg, tmp_path):
    await make_sandbox_row(sid, tool_id="t1", config_path=cfg,
                     compose_project="existing-project", config_hash="stale")
    calls = []

    async def mock_run(*args, **kwargs):
        calls.append(args)
        return OK

    with patch_docker(side_effect=mock_run):
        await start_sandbox(sid, "t1", cfg, str(tmp_path))
    assert any("up" in c for c in calls)
    row = await sandbox_rows.get(sid, "t1")
    assert row is not None and row.config_hash == _config_hash(cfg)


async def test_creates_row_keyed_on_sandbox_id_defaulting_to_tool_id(sid, cfg, tmp_path):
    with patch_docker():
        result = await start_sandbox(sid, "python_lab", cfg, str(tmp_path), sandbox_id="python_lab_uv")
    assert result.startswith("hg")
    row = await sandbox_rows.get(sid, "python_lab_uv")
    assert row is not None and row.status == "running"
    assert await sandbox_rows.get(sid, "python_lab") is None
    with patch_docker():
        await start_sandbox(sid, "python_lab", cfg, str(tmp_path))
    assert await sandbox_rows.get(sid, "python_lab") is not None


async def test_creates_external_volumes_before_up(sid, tmp_path):
    config_file = tmp_path / "sandbox.yaml"
    config_file.write_text(
        "services:\n  app:\n    image: ubuntu\n"
        "volumes:\n  uv-cache:\n    name: hypergolic-shared-uv-cache\n    external: true\n"
    )
    calls = []

    async def mock_run(*args, **kwargs):
        calls.append(args)
        return OK

    with patch_docker(side_effect=mock_run):
        await start_sandbox(sid, "new-tool", str(config_file), str(tmp_path))

    volume_creates = [c for c in calls if c[:2] == ("volume", "create")]
    assert volume_creates == [("volume", "create", "hypergolic-shared-uv-cache")]
    up_index = next(i for i, c in enumerate(calls) if "up" in c)
    assert calls.index(volume_creates[0]) < up_index


@pytest.mark.parametrize("fail_with, match", [
    (ExecResult(stdout="", stderr="Container failed", returncode=1), "Failed to start"),
    (RuntimeError("unexpected"), "unexpected"),
])
async def test_up_failure_marks_error(sid, cfg, tmp_path, fail_with, match):
    async def mock_run(*args, **kwargs):
        if args[:1] == ("info",):
            return OK
        if isinstance(fail_with, Exception):
            raise fail_with
        return fail_with

    with patch_docker(side_effect=mock_run), pytest.raises(SandboxError, match=match):
        await start_sandbox(sid, "fail-tool", cfg, str(tmp_path))

    sandbox = await sandbox_rows.get(sid, "fail-tool")
    assert sandbox is not None and sandbox.status == "error"


BUILD_CFG = "services:\n  app:\n    image: hg-app:latest\n    build:\n      context: .\n"


async def test_build_runs_before_up_on_its_own_timeout(sid, tmp_path):
    config_file = tmp_path / "sandbox.yaml"
    config_file.write_text(BUILD_CFG)
    docker_mock = AsyncMock(return_value=OK)
    with patch_docker(side_effect=docker_mock):
        await start_sandbox(sid, "my-tool", str(config_file), str(tmp_path))

    stages = [
        call.args[call.args.index("-f") + 2]
        for call in docker_mock.await_args_list
        if "compose" in call.args
    ]
    assert stages.index("build") < stages.index("up")
    build_call = next(c for c in docker_mock.await_args_list if "build" in c.args)
    assert build_call.kwargs["timeout"] == BUILD_TIMEOUT_SECONDS


async def test_skips_build_for_pulled_images(sid, cfg, tmp_path):
    docker_mock = AsyncMock(return_value=OK)
    with patch_docker(side_effect=docker_mock):
        await start_sandbox(sid, "my-tool", cfg, str(tmp_path))
    assert not any("build" in call.args for call in docker_mock.await_args_list)


async def test_cancelled_mid_build_tears_down(sid, tmp_path):
    config_file = tmp_path / "sandbox.yaml"
    config_file.write_text(BUILD_CFG)

    async def mock_run(*args, **kwargs):
        if "build" in args:
            raise asyncio.CancelledError()
        return OK

    with patch_docker(side_effect=mock_run):
        with pytest.raises(asyncio.CancelledError):
            await start_sandbox(sid, "my-tool", str(config_file), str(tmp_path))
        await asyncio.gather(*_detached_tasks)
    sandbox = await sandbox_rows.get(sid, "my-tool")
    assert sandbox is not None and sandbox.status == "error"


async def test_existing_non_running_row_gets_restarted(sid, cfg, tmp_path):
    await make_sandbox_row(sid, tool_id="t2", status="error", config_path=cfg, compose_project="old-project")
    with patch_docker():
        await start_sandbox(sid, "t2", cfg, str(tmp_path))
    sandbox = await sandbox_rows.get(sid, "t2")
    assert sandbox is not None and sandbox.status == "running"


async def test_concurrent_start_runs_compose_up_once(sid, cfg, tmp_path):
    up_calls = 0
    ready = False

    async def mock_run_compose(*args, **kwargs):
        nonlocal up_calls, ready
        if "up" in args:
            await asyncio.sleep(0)
            up_calls += 1
            ready = True
            return OK
        if "ps" in args:
            return ExecResult(stdout="container-id\n" if ready else "", stderr="", returncode=0)
        return OK

    with patch_docker(), patch(COMPOSE, side_effect=mock_run_compose):
        results = await asyncio.gather(
            start_sandbox(sid, "cmd", cfg, str(tmp_path)),
            start_sandbox(sid, "cmd", cfg, str(tmp_path)),
        )

    assert up_calls == 1 and results[0] == results[1]
    sandbox = await sandbox_rows.get(sid, "cmd")
    assert sandbox is not None and sandbox.status == "running"


async def test_benign_up_conflict_is_success_when_ready(sid, cfg, tmp_path):
    async def mock_run_compose(*args, **kwargs):
        if "up" in args:
            return ExecResult(stdout="", stderr="network ... already exists", returncode=1)
        if "ps" in args:
            return ExecResult(stdout="container-id\n", stderr="", returncode=0)
        return OK

    with patch_docker(), patch(COMPOSE, side_effect=mock_run_compose):
        result = await start_sandbox(sid, "cmd", cfg, str(tmp_path))

    assert result.startswith("hg")
    sandbox = await sandbox_rows.get(sid, "cmd")
    assert sandbox is not None and sandbox.status == "running"


async def test_failed_up_leaves_no_leftovers(sid, tmp_path):
    config_file = tmp_path / "sandbox.yaml"
    config_file.write_text(
        "services:\n  app:\n    image: ubuntu\n    labels:\n      hypergolic.expose: api=8000\n"
    )
    calls: list[tuple] = []

    async def mock_run(*args, **kwargs):
        calls.append(args)
        if args[:1] == ("info",) or "down" in args:
            return OK
        return ExecResult(stdout="", stderr="boom", returncode=1)

    with patch_docker(side_effect=mock_run), pytest.raises(SandboxError):
        await start_sandbox(sid, "leak-tool", str(config_file), str(tmp_path))

    assert not [p.name for p in tmp_path.iterdir() if p.name.startswith(".hg-resolved-")]
    sandbox = await sandbox_rows.get(sid, "leak-tool")
    assert sandbox is not None and sandbox.status == "error"
    assert any("down" in c for c in calls)


async def test_row_keeps_canonical_path_and_port_map(sid, tmp_path):
    config_file = tmp_path / "acme.compose.yaml"
    config_file.write_text(
        "services:\n  api:\n    image: ubuntu\n    labels:\n      hypergolic.expose: api=8000\n"
    )

    async def mock_run(*args, **kwargs):
        if args[:1] == ("compose",) and "port" in args:
            return ExecResult(stdout="127.0.0.1:54999", stderr="", returncode=0)
        return OK

    with patch_docker(side_effect=mock_run):
        await start_sandbox(sid, "acme-tool", str(config_file), str(tmp_path))

    sandbox = await sandbox_rows.get(sid, "acme-tool")
    assert sandbox is not None
    assert sandbox.config_path == str(config_file)
    assert sandbox.port_map == {"api": 54999}


async def test_start_refuses_ended_session(sid, cfg):
    session_rows.update(sid, status="concluded")
    with pytest.raises(SandboxError, match="ended"):
        await start_sandbox(sid, "t1", cfg, "/workspace")
