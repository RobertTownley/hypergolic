from unittest.mock import AsyncMock

import pytest

from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sessions import session_rows
from hypergolic.sandbox.manager.exec import exec_in_sandbox
from hypergolic.sandbox.manager.types import ExecResult, SandboxError

from .conftest import OK, make_sandbox_row, patch_docker

DOWN = ExecResult(stdout="", stderr='service "app" is not running', returncode=1)
INFO_OK = ExecResult(stdout="Docker info", stderr="", returncode=0)


@pytest.mark.parametrize("status, compose_project, match", [
    (None, None, "starting up"),
    ("error", "hg-x", "error state"),
    ("pending", "hg-x", "starting up"),
    ("stopped", "hg-x", "'stopped' state"),
    ("running", None, "no compose project"),
])
async def test_guard_errors(sid, status, compose_project, match):
    if status is not None:
        await make_sandbox_row(sid, status=status, config_path="/fake", compose_project=compose_project)
    with pytest.raises(SandboxError, match=match):
        await exec_in_sandbox(sid, "my-tool", "ls")


async def test_success(sid, cfg):
    await make_sandbox_row(sid, config_path=cfg, compose_project="hg-my_tool-abc")
    with patch_docker(ExecResult(stdout="hello", stderr="", returncode=0)):
        result = await exec_in_sandbox(sid, "my-tool", "echo hello")
    assert result.stdout == "hello" and result.returncode == 0


async def test_recovers_after_container_down(sid, cfg, tmp_path):
    await make_sandbox_row(sid, config_path=cfg, compose_project="hg-my_tool-abc")
    success = ExecResult(stdout="hello", stderr="", returncode=0)
    docker_mock = AsyncMock(side_effect=[DOWN, INFO_OK, OK, success])
    with patch_docker(side_effect=docker_mock):
        result = await exec_in_sandbox(sid, "my-tool", "echo hello", project_root=str(tmp_path))

    assert result.returncode == 0 and result.stdout == "hello"
    up_call = docker_mock.call_args_list[2]
    assert up_call.kwargs["env"]["HYPERGOLIC_WORKSPACE"] == str(tmp_path)
    assert "HYPERGOLIC_HARNESS" in up_call.kwargs["env"]
    recovered = await sandbox_rows.get(sid, "my-tool")
    assert recovered is not None and recovered.status == "running"


async def test_no_recovery_without_project_root(sid, cfg):
    await make_sandbox_row(sid, config_path=cfg, compose_project="hg-my_tool-abc")
    docker_mock = AsyncMock(return_value=DOWN)
    with patch_docker(side_effect=docker_mock):
        result = await exec_in_sandbox(sid, "my-tool", "echo hello")
    assert result.returncode == 1 and docker_mock.await_count == 1


async def test_recovery_failure_marks_error(sid, cfg, tmp_path):
    await make_sandbox_row(sid, config_path=cfg, compose_project="hg-my_tool-abc")
    up_fail = ExecResult(stdout="", stderr="build failed", returncode=1)
    not_ready = ExecResult(stdout="", stderr="", returncode=0)
    with patch_docker(side_effect=AsyncMock(side_effect=[DOWN, INFO_OK, up_fail, not_ready])):
        result = await exec_in_sandbox(sid, "my-tool", "echo hello", project_root=str(tmp_path))

    assert result.returncode == 1
    errored = await sandbox_rows.get(sid, "my-tool")
    assert errored is not None and errored.status == "error"


async def test_recovery_cleans_resolved_config_on_failure(sid, tmp_path):
    config_file = tmp_path / "acme.compose.yaml"
    config_file.write_text(
        "services:\n  app:\n    image: ubuntu\n    labels:\n      hypergolic.expose: api=8000\n"
    )
    await make_sandbox_row(sid, tool_id="rec-tool", config_path=str(config_file), compose_project="hg-rec-abc")
    up_fail = ExecResult(stdout="", stderr="build failed", returncode=1)
    not_ready = ExecResult(stdout="", stderr="", returncode=0)
    with patch_docker(side_effect=AsyncMock(side_effect=[DOWN, INFO_OK, up_fail, not_ready])):
        await exec_in_sandbox(sid, "rec-tool", "ls", project_root=str(tmp_path))

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".hg-resolved-")]
    assert leftovers == []


async def test_recovery_missing_config_fails_gracefully(sid, tmp_path):
    missing = tmp_path / "gone.compose.yaml"
    await make_sandbox_row(sid, tool_id="gone-tool", config_path=str(missing), compose_project="hg-gone-abc")
    with patch_docker(side_effect=AsyncMock(side_effect=[DOWN, INFO_OK])):
        result = await exec_in_sandbox(sid, "gone-tool", "ls", project_root=str(tmp_path))

    assert result.returncode == 1
    errored = await sandbox_rows.get(sid, "gone-tool")
    assert errored is not None and errored.status == "error"


async def test_targets_container_and_workdir(sid, tmp_path):
    config_file = tmp_path / "sandbox.yaml"
    config_file.write_text("services:\n  api:\n    image: ubuntu\n  frontend:\n    image: node\n")
    await make_sandbox_row(sid, config_path=str(config_file), compose_project="hg-my_tool-abc")
    captured = {}

    async def mock_run(*args, **kwargs):
        captured["args"] = args
        return ExecResult(stdout="ok", stderr="", returncode=0)

    with patch_docker(side_effect=mock_run):
        await exec_in_sandbox(sid, "my-tool", "ls", container="frontend", workdir="/app")

    args = captured["args"]
    assert "frontend" in args and "api" not in args
    assert "-w" in args and args[args.index("-w") + 1] == "/app"

    with pytest.raises(SandboxError, match="not defined in this sandbox"):
        await exec_in_sandbox(sid, "my-tool", "ls", container="nope")


async def test_no_recovery_for_ended_session(sid, cfg, tmp_path):
    await make_sandbox_row(sid, config_path=cfg, compose_project="hg-my_tool-abc")
    session_rows.update(sid, status="concluded")
    docker_mock = AsyncMock(side_effect=[DOWN, INFO_OK])
    with patch_docker(side_effect=docker_mock):
        result = await exec_in_sandbox(sid, "my-tool", "ls", project_root=str(tmp_path))
    assert result.returncode != 0
    assert docker_mock.call_count == 2
