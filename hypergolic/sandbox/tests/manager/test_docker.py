import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hypergolic.sandbox.manager.docker import _run_docker, ensure_docker_available
from hypergolic.sandbox.manager.compose_env import compose_env as _compose_env
from hypergolic.sandbox.manager.types import ExecResult, SandboxError, SandboxTimeout, SandboxUnavailableError
from tests.conftest import make_project, make_session

from .conftest import patch_docker


def _fake_proc(stdout=b"", stderr=b"", returncode=0, eof=True):
    proc = MagicMock(returncode=returncode)
    for name, data in (("stdout", stdout), ("stderr", stderr)):
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        if eof:
            reader.feed_eof()
        setattr(proc, name, reader)
    proc.wait = AsyncMock(return_value=returncode)
    proc.kill = MagicMock()
    return proc


@pytest.mark.parametrize("returncode", [0, None])
async def test_run_docker_success(returncode):
    proc = _fake_proc(stdout=b"output", returncode=returncode)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await _run_docker("info")
    assert result.returncode == 0 and result.stdout == "output"


async def test_run_docker_streams_chunks_live():
    proc = _fake_proc(stdout=b"out", stderr=b"err")
    seen = []

    async def on_chunk(stream, text):
        seen.append((stream, text))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        await _run_docker("info", on_chunk=on_chunk)
    assert sorted(seen) == [("stderr", "err"), ("stdout", "out")]


async def test_run_docker_timeout_carries_partial_output():
    proc = _fake_proc(stdout=b"partial", eof=False)
    with (
        patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
        patch("hypergolic.sandbox.manager.docker._TICK_SECONDS", 0.01),
        pytest.raises(SandboxTimeout, match="timed out") as excinfo,
    ):
        await _run_docker("info", timeout=0.05)
    assert excinfo.value.stdout == "partial"
    proc.kill.assert_called_once()


async def test_ensure_docker_available_ok():
    with patch_docker(ExecResult(stdout="Docker info...", stderr="", returncode=0)):
        await ensure_docker_available()


@pytest.mark.parametrize("docker_mock, match", [
    (AsyncMock(return_value=ExecResult(stdout="", stderr="Cannot connect", returncode=1)), "not running"),
    (AsyncMock(side_effect=FileNotFoundError()), "not found"),
    (AsyncMock(side_effect=SandboxError("timed out")), "not responding"),
])
async def test_ensure_docker_available_failures(docker_mock, match):
    with patch("hypergolic.sandbox.manager.docker._run_docker", docker_mock):
        with pytest.raises(SandboxUnavailableError, match=match):
            await ensure_docker_available()


async def test_compose_env(_no_disk_shared_dir):
    make_project("p1")
    sid = make_session(project_id="p1")

    env = await _compose_env(sid, "/some/worktree")
    assert env["HYPERGOLIC_WORKSPACE"] == "/some/worktree"
    assert env["HYPERGOLIC_SHARED"].endswith(f"/sessions/{sid}/shared")
    assert env["HYPERGOLIC_HOST_REPO_SHARED"].endswith("/shared/p1/.git")
    assert env["HYPERGOLIC_QUARANTINE_SHARED"].endswith(f"/quarantine/{sid}/shared.git")
    _no_disk_shared_dir.assert_called_once_with("p1")

    env = await _compose_env("no-such-session", "/wt")
    assert "HYPERGOLIC_SHARED" not in env and env["HYPERGOLIC_WORKSPACE"] == "/wt"
    _no_disk_shared_dir.assert_called_once()
