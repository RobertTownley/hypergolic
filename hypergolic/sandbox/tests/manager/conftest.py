from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.db.models import DBSandbox
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sandbox.manager.types import ExecResult
from tests.conftest import make_project, make_session

DOCKER = "hypergolic.sandbox.manager.docker._run_docker"
COMPOSE = "hypergolic.sandbox.manager.docker._run_compose"
OK = ExecResult(stdout="", stderr="", returncode=0)


def patch_docker(result=OK, side_effect=None):
    if side_effect is not None:
        return patch(DOCKER, side_effect=side_effect)
    return patch(DOCKER, AsyncMock(return_value=result))


async def make_sandbox_row(
    session_id: str, tool_id: str = "my-tool", status: str = "running", *,
    config_path: str = "/fake/sandbox.yaml", compose_project: str | None = "hg-my_tool-abc123", **fields,
) -> DBSandbox:
    return await sandbox_rows.create(
        session_id, tool_id, status=status, config_path=config_path, compose_project=compose_project, **fields,
    )


@pytest.fixture
def sid():
    make_project("p1")
    return make_session(project_id="p1")


@pytest.fixture
def cfg(tmp_path):
    f = tmp_path / "sandbox.yaml"
    f.write_text("services:\n  app:\n    image: ubuntu\n")
    return str(f)


@pytest.fixture(autouse=True)
def _no_disk_shared_dir(tmp_path):
    with (
        patch(
            "hypergolic.sandbox.manager.compose_env.ensure_shared_dir",
            side_effect=lambda project_id: tmp_path / "shared" / project_id,
        ) as m,
        patch(
            "hypergolic.sandbox.manager.compose_env.session_shared_workspace",
            side_effect=lambda sid: tmp_path / "sessions" / sid / "shared",
        ),
        patch(
            "hypergolic.sandbox.manager.compose_env.ensure_quarantine",
            side_effect=lambda *, session_id, repo, host_gitdir:
                tmp_path / "quarantine" / session_id / f"{repo}.git",
        ),
    ):
        yield m
