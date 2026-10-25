import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.websocket.conclude import handle_conclude_session
from hypergolic.websocket.schemas import ConcludeSessionMessage
from hypergolic.websocket.turn_manager import TurnManager
from tests.conftest import make_project, make_session
from tests.helpers.git import init_repo, run_git
from hypergolic.git.sandbox_repo import hypergolic_ref
from hypergolic.git.tests._worktree_thread_helpers import join_worktree_threads


@pytest.fixture(autouse=True)
def _sandbox_running():
    with patch(
        "hypergolic.dispatch.conclude.worktree.session_container",
        AsyncMock(return_value="ws-container"),
    ):
        yield


def _make_msg(
    session_id="s-1",
    rating=4,
    feedback="good",
    delete_worktree=True,
    delete_branch=True,
    analyze_learnings=False,
):
    return ConcludeSessionMessage(
        session_id=session_id,
        rating=rating,
        feedback=feedback,
        delete_worktree=delete_worktree,
        delete_branch=delete_branch,
        analyze_learnings=analyze_learnings,
    )


def _setup_workspace(tmp_path: Path, sid: str, pid: str):
    repo = tmp_path / "proj"
    init_repo(repo)
    make_project(pid, "P", str(repo))
    ws_dir = tmp_path / f"ws-{sid}"
    ws_dir.mkdir()
    branch = f"main-{sid}"
    make_session(sid=sid, project_id=pid, worktree_path=str(ws_dir), worktree_branch=branch)
    return repo, ws_dir, branch


def _ref_exists(repo: Path, ref: str) -> bool:
    import subprocess

    try:
        run_git(repo, "rev-parse", "--verify", "--quiet", ref)
    except subprocess.CalledProcessError:
        return False
    return True


@patch("hypergolic.websocket.conclude.cancel_child_dispatches")
async def test_conclude_basic(mock_cancel, broadcast, session_rows):
    ws = AsyncMock()
    tm = TurnManager()
    row = session_rows[make_session(sid="s-1")]

    msg = _make_msg()
    await handle_conclude_session(msg, ws, tm, broadcast)

    mock_cancel.assert_called_once_with("s-1")
    broadcast.assert_called_once()
    event = broadcast.call_args[0][0]
    assert event.type == "session_status_change"

    ws.send_json.assert_called_once()
    sent = ws.send_json.call_args[0][0]
    assert sent["type"] == "session_concluded"
    assert sent["conclusion_rating"] == 4
    assert sent["conclusion_feedback"] == "good"
    assert (row.status, row.conclusion_rating, row.conclusion_feedback) == ("concluded", 4, "good")
    assert row.concluded_at is not None


@patch("hypergolic.websocket.conclude.cancel_child_dispatches")
async def test_conclude_is_a_noop_while_already_concluding(mock_cancel, broadcast):
    make_session(sid="s-1", status="concluding")
    ws = AsyncMock()
    await handle_conclude_session(_make_msg(), ws, TurnManager(), broadcast)
    mock_cancel.assert_not_called()
    ws.send_json.assert_not_called()


@patch("hypergolic.websocket.conclude.end_children", new_callable=AsyncMock)
@patch("hypergolic.websocket.conclude.cancel_child_dispatches")
async def test_conclude_ends_children_through_child_end(mock_cancel, mock_end, broadcast):
    ws = AsyncMock()
    tm = TurnManager()
    await handle_conclude_session(_make_msg(), ws, tm, broadcast)

    mock_end.assert_awaited_once_with("s-1", broadcast, tm.cancel_existing_turn)


@pytest.mark.timeout(2)
@patch("hypergolic.websocket.conclude.cancel_child_dispatches")
async def test_conclude_cancels_active_turn(mock_cancel, broadcast, monkeypatch):
    monkeypatch.setattr("hypergolic.websocket.turn_manager.CANCEL_GRACE", 0.01)
    ws = AsyncMock()
    tm = TurnManager()

    async def long_coro(cancel_event: asyncio.Event) -> None:
        await asyncio.sleep(10)

    tm.start_turn("s-1", long_coro)

    msg = _make_msg()
    await handle_conclude_session(msg, ws, tm, broadcast)

    assert "s-1" not in tm.session_tasks or tm.session_tasks["s-1"].done()


@pytest.mark.timeout(15)
async def test_conclude_tears_down_clean_worktree(tmp_path, broadcast):
    repo, ws_dir, branch = _setup_workspace(tmp_path, "s-wc", "p-wc")
    ref = hypergolic_ref("p-wc", branch)
    run_git(repo, "update-ref", ref, "main")

    ws = AsyncMock()
    tm = TurnManager()

    with patch("hypergolic.websocket.conclude.cancel_child_dispatches"):
        await handle_conclude_session(_make_msg(session_id="s-wc"), ws, tm, broadcast)

    join_worktree_threads()
    assert not ws_dir.exists()
    assert not _ref_exists(repo, ref)
    assert ws.send_json.call_count == 1
    assert ws.send_json.call_args[0][0]["type"] == "session_concluded"


@pytest.mark.timeout(15)
async def test_conclude_dirty_worktree_still_concludes(tmp_path, broadcast):
    repo, ws_dir, branch = _setup_workspace(tmp_path, "s-wd", "p-wd")
    (ws_dir / "uncommitted.txt").write_text("wip")

    ws = AsyncMock()
    tm = TurnManager()

    with patch("hypergolic.websocket.conclude.cancel_child_dispatches"):
        await handle_conclude_session(_make_msg(session_id="s-wd"), ws, tm, broadcast)

    join_worktree_threads()
    assert not ws_dir.exists()
    assert ws.send_json.call_args[0][0]["type"] == "session_concluded"


@pytest.mark.timeout(15)
async def test_conclude_failed_fetch_back_returns_conclude_error(tmp_path, broadcast, session_rows):
    from hypergolic.git.sandbox_integrate import SandboxGitError

    repo, ws_dir, branch = _setup_workspace(tmp_path, "s-ns", "p-ns")

    ws = AsyncMock()
    tm = TurnManager()

    with (
        patch("hypergolic.websocket.conclude.cancel_child_dispatches"),
        patch(
            "hypergolic.dispatch.conclude.worktree.refresh_session_ref",
            AsyncMock(side_effect=SandboxGitError("quarantine unreachable")),
        ),
    ):
        await handle_conclude_session(
            _make_msg(session_id="s-ns", delete_branch=False), ws, tm, broadcast,
        )

    assert ws_dir.exists()
    assert ws.send_json.call_count == 1
    payload = ws.send_json.call_args[0][0]
    assert payload["type"] == "conclude_error"
    assert "quarantine unreachable" in payload["detail"]
    broadcast.assert_not_called()
    row = session_rows["s-ns"]
    assert row.status != "concluded"
    assert row.concluded_at is None


@pytest.mark.timeout(15)
async def test_conclude_delete_worktree_false_keeps_directory(tmp_path, broadcast, session_rows):
    repo, ws_dir, branch = _setup_workspace(tmp_path, "s-wk", "p-wk")
    ref = hypergolic_ref("p-wk", branch)
    main = run_git(repo, "rev-parse", "main").stdout.strip()
    tree = run_git(repo, "rev-parse", "main^{tree}").stdout.strip()
    new_commit = run_git(repo, "commit-tree", tree, "-p", main, "-m", "w").stdout.strip()
    run_git(repo, "update-ref", ref, new_commit)

    ws = AsyncMock()
    tm = TurnManager()

    msg = _make_msg(
        session_id="s-wk", delete_worktree=False, delete_branch=False,
    )
    refresh = patch(
        "hypergolic.dispatch.conclude.worktree.refresh_session_ref",
        AsyncMock(return_value=ref),
    )
    base = patch(
        "hypergolic.dispatch.conclude.worktree.base_ref_for",
        AsyncMock(return_value="refs/heads/main"),
    )
    with patch("hypergolic.websocket.conclude.cancel_child_dispatches"), refresh, base:
        await handle_conclude_session(msg, ws, tm, broadcast)

    assert ws_dir.exists()
    assert _ref_exists(repo, ref)
    row = session_rows["s-wk"]
    assert row.status == "concluded"
    assert row.worktree_path is not None
    assert row.worktree_status is None
    assert ws.send_json.call_args[0][0]["type"] == "session_concluded"


@patch("hypergolic.websocket.conclude.schedule_session_sandbox_cleanup")
@patch("hypergolic.websocket.conclude.cancel_child_dispatches")
async def test_conclude_schedules_sandbox_cleanup(mock_cancel, mock_sched, broadcast):
    await handle_conclude_session(_make_msg(), AsyncMock(), TurnManager(), broadcast)

    mock_sched.assert_called_once_with("s-1")


@patch("hypergolic.websocket.conclude.schedule_session_sandbox_cleanup")
@patch("hypergolic.websocket.conclude.maybe_dispatch_distillation", new_callable=AsyncMock)
@patch("hypergolic.websocket.conclude.should_distill", new_callable=AsyncMock, return_value=True)
@patch("hypergolic.websocket.conclude.cancel_child_dispatches")
async def test_distilling_conclude_defers_sandbox_cleanup(
    mock_cancel, mock_should, mock_distill, mock_sched, broadcast,
):
    make_session(sid="s-1")
    with patch("hypergolic.websocket.conclude.teardown_worktree_at_conclude", new_callable=AsyncMock):
        await handle_conclude_session(_make_msg(analyze_learnings=True), AsyncMock(), TurnManager(), broadcast)

    mock_sched.assert_not_called()
    await asyncio.sleep(0)
    mock_distill.assert_awaited_once()
