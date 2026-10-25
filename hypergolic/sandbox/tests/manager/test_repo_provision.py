from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.sandbox.manager import repo_creation as rc
from hypergolic.sandbox.manager import repo_provision as rp
from hypergolic.sandbox.manager.repo_report import RepoProvisionError, pop_report_warnings
from hypergolic.sandbox.manager.types import ExecResult
from hypergolic.sessions.operations import load_session


OK = ExecResult(stdout="", stderr="", returncode=0)
MISSING = ExecResult(stdout="", stderr="", returncode=1)


@pytest.fixture
def env(sid, tmp_path):
    session = load_session(sid)
    project = rp._find_project(session.project_id)
    assert project is not None
    with (
        patch.object(rp, "host_git_identity", return_value=("U", "u@x")),
        patch.object(rp, "settings_harness_gitdir", return_value=None),
        patch.object(rp, "shared_dir", return_value=tmp_path / "no-shared"),
    ):
        yield session, project


def _exec_recorder(results_by_match: list[tuple[str, ExecResult]]):
    calls: list[str] = []

    async def _run(**kwargs):
        assert kwargs.get("project_root") is None
        command = kwargs["command"]
        calls.append(command)
        for needle, result in results_by_match:
            if needle in command:
                return result
        return OK

    return AsyncMock(side_effect=_run), calls


async def test_heals_existing_app_clone(env):
    session, project = env
    mock, calls = _exec_recorder([(rp.APP_OPENS_PROBE, OK)])
    with patch.object(rp, "exec_in_sandbox", mock):
        steps = await rp.provision_sandbox(session, project)

    app, harness, shared = steps
    assert (app.repo, app.action, app.ok) == ("app", "heal", True)
    assert (harness.ok, shared.ok) == (None, None)
    heal = calls[-1]
    assert "remote set-url origin" in heal and "git clone" not in heal


async def test_clones_missing_app_repo(env):
    session, project = env
    mock, calls = _exec_recorder([("set -e", OK), (rp.APP_OPENS_PROBE, MISSING)])
    with (
        patch.object(rp, "exec_in_sandbox", mock),
        patch.object(rc, "_resolve_base_ref", AsyncMock(return_value="refs/heads/main")),
    ):
        steps = await rp.provision_sandbox(session, project)
    assert (steps[0].action, steps[0].ok) == ("clone", True)
    assert "git clone" in calls[-1]


async def test_unresolvable_base_is_a_failed_step_not_a_raise(env):
    session, project = env
    mock, _ = _exec_recorder([("set -e", OK), (rp.APP_OPENS_PROBE, MISSING)])
    with (
        patch.object(rp, "exec_in_sandbox", mock),
        patch.object(
            rc, "_resolve_base_ref",
            AsyncMock(side_effect=RepoProvisionError("no base")),
        ),
    ):
        steps = await rp.provision_sandbox(session, project)
    assert steps[0].ok is False and "no base" in steps[0].detail


async def test_shared_repo_retro_provisioned_when_project_repo_exists(env, tmp_path):
    session, project = env
    shared = tmp_path / "shared-repo"
    (shared / ".git").mkdir(parents=True)
    mock, calls = _exec_recorder([(rp.APP_OPENS_PROBE, OK)])
    with (
        patch.object(rp, "shared_dir", return_value=shared),
        patch.object(rp, "exec_in_sandbox", mock),
    ):
        steps = await rp.provision_sandbox(session, project)
    step = next(s for s in steps if s.repo == "shared")
    assert (step.action, step.ok) == ("ensure", True)
    assert any("/shared" in c and "git clone" in c for c in calls)


async def test_creation_path_requires_app_step(env):
    session, project = env
    mock, _ = _exec_recorder([
        ("remote set-url", ExecResult(stdout="", stderr="boom", returncode=1)),
    ])
    with (
        patch.object(rc, "ensure_session_sandbox", AsyncMock()),
        patch.object(rp, "exec_in_sandbox", mock),
        pytest.raises(RepoProvisionError, match="boom"),
    ):
        await rc.provision_session_repos(session, project)


async def test_failures_are_logged_and_popped_once(env, caplog):
    session, project = env
    mock, _ = _exec_recorder([
        ("remote set-url", ExecResult(stdout="", stderr="relic gitdir", returncode=1)),
    ])
    with patch.object(rp, "exec_in_sandbox", mock):
        await rp.provision_sandbox(session, project)
    warnings = pop_report_warnings(session.id)
    assert warnings and "relic gitdir" in warnings[0]
    assert pop_report_warnings(session.id) == []
