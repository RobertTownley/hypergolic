import asyncio
from unittest.mock import AsyncMock

from unittest.mock import patch

import pytest

from hypergolic.dispatch.runner import CONCLUDE_INSTRUCTION, dispatch, send_turn
from hypergolic.dispatch.state import (
    DispatchResult,
    _child_to_parent,
    _pending_dispatches,
    register_turn_runner,
)
from hypergolic.enums import ModelTier
from tests.conftest import make_project, make_session
from hypergolic.harness.primitives.bundles import Role
import hypergolic.dispatch.state as _state
from tests.helpers.git import init_repo, run_git
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.config.settings import settings
from hypergolic.sessions.operations import load_session


_FAKE_CHILD_PAYLOAD = {"id": "child-x", "role": "worker"}


def _clear():
    _pending_dispatches.clear()
    _child_to_parent.clear()


async def test_send_turn_raises_without_turn_runner():
    original = _state._turn_runner
    try:
        _state._turn_runner = None
        with pytest.raises(RuntimeError, match="No turn runner registered"):
            await send_turn(
                child_session_id="child-1",
                parent_session_id="parent-1",
                message="hi",
                broadcast=AsyncMock(),
            )
    finally:
        _state._turn_runner = original


async def test_send_turn_resolves_on_conclude():
    _clear()
    resolved = DispatchResult(outcome="success", conclusion="done")

    def fake_runner(session_id, message):
        future = _pending_dispatches.get(session_id)
        if future and not future.done():
            future.set_result(resolved)

    with patch("hypergolic.dispatch.runner._build_child_session_payload", return_value=_FAKE_CHILD_PAYLOAD):
        register_turn_runner(fake_runner)
        result = await send_turn(
            child_session_id="child-ok",
            parent_session_id="parent-ok",
            message="go",
            broadcast=AsyncMock(),
        )
    assert result.outcome == "success"
    assert result.conclusion == "done"
    assert "child-ok" not in _pending_dispatches


async def test_send_turn_emits_dispatch_started():
    _clear()
    resolved = DispatchResult(outcome="success", conclusion="done")
    broadcast = AsyncMock()

    def fake_runner(session_id, message):
        future = _pending_dispatches.get(session_id)
        if future and not future.done():
            future.set_result(resolved)

    with patch("hypergolic.dispatch.runner._build_child_session_payload", return_value=_FAKE_CHILD_PAYLOAD):
        register_turn_runner(fake_runner)
        await send_turn(
            child_session_id="child-bt",
            parent_session_id="parent-bt",
            message="go",
            broadcast=broadcast,
        )

    broadcast.assert_called_once()
    event = broadcast.call_args[0][0]
    assert event.type == "dispatch_started"
    assert event.session_id == "parent-bt"


async def test_send_turn_propagates_cancellation():
    _clear()

    def fake_runner(session_id, message):
        pass

    with patch("hypergolic.dispatch.runner._build_child_session_payload", return_value=_FAKE_CHILD_PAYLOAD), \
         patch("hypergolic.dispatch.runner.schedule_session_sandbox_cleanup"):
        register_turn_runner(fake_runner)

        async def _drive():
            return await send_turn(
                child_session_id="child-cancel",
                parent_session_id="parent-cancel",
                message="hi",
                broadcast=AsyncMock(),
            )

        task = asyncio.create_task(_drive())
        await asyncio.sleep(0)
        task.cancel()

        try:
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            _pending_dispatches.pop("child-cancel", None)
            _child_to_parent.pop("child-cancel", None)


async def test_dispatch_raises_without_turn_runner():
    _clear()
    original = _state._turn_runner
    try:
        _state._turn_runner = None
        with pytest.raises(RuntimeError, match="No turn runner registered"):
            await dispatch(
                parent_session_id="p1",
                content_blocks=[],
                dispatch_prompt="do something",
                broadcast=AsyncMock(),
                role="worker",
            )
    finally:
        _state._turn_runner = original


@pytest.mark.timeout(10)
async def test_dispatch_creates_child_and_awaits_result(tmp_path, monkeypatch):
    _clear()

    app = App()
    app.register_role(Role(id="generalist", name="Generalist", prompt="test"))
    set_app(app)

    repo = tmp_path / "proj"
    init_repo(repo)

    monkeypatch.setattr(settings, "HYPERGOLIC_WORKTREES_ROOT", str(tmp_path / "wt"))

    make_project("p1", "Proj", str(repo))

    parent_ws = tmp_path / "ws-parent-d1"
    parent_ws.mkdir()
    make_session(
        project_id="p1", sid="parent-d1",
        worktree_path=str(parent_ws),
        worktree_branch="main-parent-d1",
        base_branch="main",
    )

    resolved = DispatchResult(outcome="success", conclusion="All done")
    broadcast = AsyncMock()

    child_tiers: list = []

    def fake_runner(session_id, user_message):
        child_tiers.append(load_session(session_id).model_tier)
        future = _pending_dispatches.get(session_id)
        if future and not future.done():
            future.set_result(resolved)

    register_turn_runner(fake_runner)
    result = await dispatch(
        parent_session_id="parent-d1",
        content_blocks=[{"type": "text", "text": "Do it"}],
        dispatch_prompt="You are a worker",
        broadcast=broadcast,
        role="worker",
    )

    assert result.outcome == "success"
    assert child_tiers == [ModelTier.MEDIUM]
    broadcast.assert_called()
    event = broadcast.call_args[0][0]
    assert event.type == "dispatch_started"


@pytest.mark.timeout(10)
async def test_dispatch_appends_conclude_instruction(tmp_path, monkeypatch):
    _clear()

    app = App()
    app.register_role(Role(id="generalist", name="Generalist", prompt="test"))
    set_app(app)

    repo = tmp_path / "proj2"
    init_repo(repo)

    monkeypatch.setattr(settings, "HYPERGOLIC_WORKTREES_ROOT", str(tmp_path / "wt2"))

    make_project("p1", "Proj", str(repo))

    parent_ws = tmp_path / "ws-parent-d2"
    parent_ws.mkdir()
    make_session(
        project_id="p1", sid="parent-d2",
        worktree_path=str(parent_ws),
        worktree_branch="main-parent-d2",
        base_branch="main",
    )

    received_prompts: list[str] = []

    def fake_runner(session_id, user_message):
        session = load_session(session_id)
        if session.dispatch_prompt:
            received_prompts.append(session.dispatch_prompt)
        future = _pending_dispatches.get(session_id)
        if future and not future.done():
            future.set_result(DispatchResult(outcome="success", conclusion="ok"))

    register_turn_runner(fake_runner)
    await dispatch(
        parent_session_id="parent-d2",
        content_blocks=[],
        dispatch_prompt="Base prompt",
        broadcast=AsyncMock(),
        role="worker",
    )

    assert len(received_prompts) == 1
    assert CONCLUDE_INSTRUCTION in received_prompts[0]


def _git_repo(path):
    init_repo(path)
    return run_git(path, "rev-parse", "HEAD").stdout.strip()


def _setup(tmp_path, monkeypatch, sid):
    _clear()
    app = App()
    app.register_role(Role(id="generalist", name="Generalist", prompt="test"))
    set_app(app)
    sha = _git_repo(tmp_path / "proj")
    monkeypatch.setattr(settings, "HYPERGOLIC_WORKTREES_ROOT", str(tmp_path / "wt"))
    make_project("p1", "Proj", str(tmp_path / "proj"))
    (tmp_path / "ws").mkdir()
    make_session(
        project_id="p1", sid=sid, worktree_path=str(tmp_path / "ws"),
        worktree_branch=f"main-{sid}", base_branch="main",
    )
    return sha


@pytest.mark.timeout(10)
async def test_dispatch_no_wait_returns_started_without_future(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "parent-nw")
    seen: list[str] = []
    register_turn_runner(lambda sid, msg: seen.append(sid))

    result = await dispatch(
        parent_session_id="parent-nw", content_blocks=[{"type": "text", "text": "go"}],
        dispatch_prompt="Base", broadcast=AsyncMock(), role="worker", wait=False,
    )

    assert result.outcome == "started" and seen == [result.child_session_id]
    assert result.child_session_id not in _pending_dispatches
    assert result.child_session_id
    child = load_session(result.child_session_id)
    assert child.parent_id == "parent-nw"
    assert CONCLUDE_INSTRUCTION not in (child.dispatch_prompt or "")


@pytest.mark.timeout(10)
async def test_dispatch_standalone_has_no_parent_and_roots_at_head(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "parent-sa")
    register_turn_runner(lambda sid, msg: None)

    result = await dispatch(
        parent_session_id="parent-sa", content_blocks=[], dispatch_prompt=None,
        broadcast=AsyncMock(), role="generalist", child=False, project_id="p1", wait=False,
    )

    assert result.child_session_id
    child = load_session(result.child_session_id)
    assert child.parent_id is None and child.origin == "dispatch"
    assert child.base_branch == "main" and child.dispatch_prompt is None


@pytest.mark.timeout(10)
async def test_dispatch_child_with_base_roots_at_the_host_branch(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "parent-base")
    register_turn_runner(lambda sid, msg: None)

    result = await dispatch(
        parent_session_id="parent-base", content_blocks=[], dispatch_prompt="Base",
        broadcast=AsyncMock(), role="generalist", base="main", wait=False,
    )

    assert result.child_session_id
    child = load_session(result.child_session_id)
    assert child.parent_id == "parent-base"
    assert child.base_branch == "main"


@pytest.mark.timeout(10)
async def test_dispatch_child_with_unknown_base_fails(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "parent-nobase")
    register_turn_runner(lambda sid, msg: None)

    with pytest.raises(ValueError, match="no-such-branch"):
        await dispatch(
            parent_session_id="parent-nobase", content_blocks=[], dispatch_prompt="Base",
            broadcast=AsyncMock(), role="generalist", base="no-such-branch", wait=False,
        )


def _setup_no_git(tmp_path, monkeypatch, sid):
    _clear()
    app = App()
    app.register_role(Role(id="generalist", name="Generalist", prompt="test"))
    set_app(app)
    monkeypatch.setattr(settings, "HYPERGOLIC_WORKTREES_ROOT", str(tmp_path / "wt"))
    make_project("p1", "Proj", str(tmp_path / "proj"))
    make_session(
        project_id="p1", sid=sid, worktree_path=str(tmp_path / "ws"),
        worktree_branch=f"main-{sid}", base_branch="main",
    )


PIN = "7" * 40


@pytest.mark.timeout(10)
async def test_dispatch_child_app_pin_roots_at_a_pin_in_the_parent_sandbox(tmp_path, monkeypatch):
    from hypergolic.dispatch import runner
    from hypergolic.git import parent_land

    _setup_no_git(tmp_path, monkeypatch, "parent-pin")
    register_turn_runner(lambda sid, msg: None)
    host_git = AsyncMock()
    monkeypatch.setattr(runner, "_resolve_commit", lambda path, ref: PIN)
    monkeypatch.setattr(runner, "_pin_branch", host_git)
    create = AsyncMock()
    monkeypatch.setattr(parent_land, "create_parent_pin", create)

    result = await dispatch(
        parent_session_id="parent-pin", content_blocks=[], dispatch_prompt="Base",
        broadcast=AsyncMock(), role="worker", wait=False, repo_pins={"app": PIN},
    )

    assert result.child_session_id
    child = load_session(result.child_session_id)
    assert child.base_branch.startswith(f"pin/{PIN[:12]}-")
    assert child.worktree_path and child.repo_pins == {"app": PIN}
    assert create.await_args is not None
    parent, _project = create.await_args.args
    assert parent.id == "parent-pin"
    assert create.await_args.kwargs == {"sha": PIN, "name": child.base_branch}
    host_git.assert_not_called()


@pytest.mark.timeout(10)
async def test_dispatch_child_app_pin_fails_before_any_session_when_the_pin_fails(tmp_path, monkeypatch):
    from hypergolic.dispatch import runner
    from hypergolic.git import parent_land
    from hypergolic.git.sandbox_integrate import SandboxGitError

    _setup_no_git(tmp_path, monkeypatch, "parent-pinfail")
    register_turn_runner(lambda sid, msg: None)
    monkeypatch.setattr(runner, "_resolve_commit", lambda path, ref: PIN)
    monkeypatch.setattr(parent_land, "create_parent_pin", AsyncMock(side_effect=SandboxGitError("down")))
    create_target = AsyncMock()
    monkeypatch.setattr(runner, "_create_target", create_target)

    with pytest.raises(SandboxGitError):
        await dispatch(
            parent_session_id="parent-pinfail", content_blocks=[], dispatch_prompt="Base",
            broadcast=AsyncMock(), role="worker", wait=False, repo_pins={"app": PIN},
        )
    create_target.assert_not_called()


@pytest.mark.timeout(10)
async def test_dispatch_standalone_app_pin_roots_at_a_host_pin_branch(tmp_path, monkeypatch):
    from hypergolic.dispatch import runner

    _setup_no_git(tmp_path, monkeypatch, "parent-sapin")
    register_turn_runner(lambda sid, msg: None)
    monkeypatch.setattr(runner, "_pin_branch", lambda path, sha: f"pin/{sha[:12]}")

    result = await dispatch(
        parent_session_id="parent-sapin", content_blocks=[], dispatch_prompt=None,
        broadcast=AsyncMock(), role="generalist", child=False, project_id="p1", wait=False,
        repo_pins={"app": PIN},
    )

    assert result.child_session_id
    child = load_session(result.child_session_id)
    assert child.parent_id is None and child.base_branch == f"pin/{PIN[:12]}"
