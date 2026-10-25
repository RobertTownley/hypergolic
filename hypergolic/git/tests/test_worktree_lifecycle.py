from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.timeout(5)

from hypergolic.git.worktree_lifecycle import (  # noqa: E402
    WorktreeUnavailableError,
    _discard_event,
    _get_or_create_event,
    _ready_events,
    _signal_ready,
    run_create_and_seed,
    run_teardown,
    schedule_create_and_seed,
    schedule_teardown,
    set_worktree_status,
    wait_for_ready,
)
from hypergolic.sessions import session_rows  # noqa: E402
from tests.conftest import make_project, make_session  # noqa: E402

PROVISION = "hypergolic.sandbox.manager.repo_creation.provision_session_repos"


@pytest.fixture(autouse=True)
def _isolate_event_registry():
    _ready_events.clear()
    yield
    _ready_events.clear()


def _seed_session_row(session_id: str, project_id: str = "proj-wl") -> None:
    make_project(project_id, "P", "/tmp/nope")
    make_session(project_id, session_id, worktree_path="/tmp/hg-test-wt", worktree_branch="main-S",
                 worktree_status="pending")


def _read_status(session_id: str) -> str | None:
    row = session_rows.fetch(session_id)
    return row.worktree_status if row else None


def _run_create(session_id: str, seed_callback=None) -> None:
    run_create_and_seed(
        session_id=session_id,
        project_id="proj-wl",
        project_path=Path("/tmp/proj"),
        base_branch="main",
        seed_callback=seed_callback,
    )


def test_set_worktree_status_writes_db():
    _seed_session_row("s-st")
    set_worktree_status("s-st", "ready")
    assert _read_status("s-st") == "ready"


def test_run_create_and_seed_without_callback_marks_ready(worktrees_home: Path):
    _seed_session_row("s-create")
    with patch(PROVISION, new=AsyncMock()) as provision:
        _run_create("s-create")
    provision.assert_awaited_once()
    assert _read_status("s-create") == "ready"
    row = session_rows.fetch_one("s-create")
    assert row.worktree_branch == "main-s-create"
    wt = Path(row.worktree_path)
    assert wt.is_relative_to(worktrees_home)
    assert wt.is_dir() and not (wt / ".git").exists()


def test_run_create_and_seed_with_async_callback_marks_ready(worktrees_home: Path):
    _seed_session_row("s-seed")
    observed: list[str] = []

    async def seed() -> None:
        assert not _get_or_create_event("s-seed").is_set()
        observed.append("s-seed")

    with patch(PROVISION, new=AsyncMock()):
        _run_create("s-seed", seed_callback=seed)
    assert observed == ["s-seed"]
    assert _read_status("s-seed") == "ready"


def test_run_create_and_seed_marks_create_failed_when_provision_raises(
    worktrees_home: Path,
):
    _seed_session_row("s-cfail")
    with patch(PROVISION, new=AsyncMock(side_effect=RuntimeError("boom"))):
        _run_create("s-cfail")
    assert _read_status("s-cfail") == "create_failed"


def test_run_create_and_seed_marks_create_failed_without_sandbox(
    worktrees_home: Path,
):
    _seed_session_row("s-nosbx", project_id="proj-nosbx")
    from hypergolic.harness.app.state import get_app

    project = get_app().find_project("proj-nosbx")
    assert project is not None
    project.configure_sandbox(None)
    run_create_and_seed(
        session_id="s-nosbx", project_id="proj-nosbx",
        project_path=Path("/tmp/proj"), base_branch="main",
    )
    assert _read_status("s-nosbx") == "create_failed"


def test_run_create_and_seed_marks_create_failed_for_unknown_project(
    worktrees_home: Path,
):
    _seed_session_row("s-unk")
    run_create_and_seed(
        session_id="s-unk", project_id="proj-ghost",
        project_path=Path("/tmp/proj"), base_branch="main",
    )
    assert _read_status("s-unk") == "create_failed"


def test_run_create_and_seed_marks_seed_failed_when_callback_raises(
    worktrees_home: Path,
):
    _seed_session_row("s-sfail")

    async def bad_seed() -> None:
        raise RuntimeError("seed bug")

    with patch(PROVISION, new=AsyncMock()):
        _run_create("s-sfail", seed_callback=bad_seed)
    assert _read_status("s-sfail") == "seed_failed"


def test_schedule_create_and_seed_runs_on_daemon_thread(worktrees_home: Path):
    _seed_session_row("s-sched")
    with patch(PROVISION, new=AsyncMock()):
        thread = schedule_create_and_seed(
            session_id="s-sched",
            project_id="proj-wl",
            project_path=Path("/tmp/proj"),
            base_branch="main",
            seed_callback=None,
        )
        assert thread.daemon
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert _read_status("s-sched") == "ready"


def test_schedule_create_and_seed_does_not_block_caller(worktrees_home: Path):
    _seed_session_row("s-nb")
    gate = threading.Event()
    caller_id = threading.get_ident()
    observed: dict[str, int] = {}

    async def slow_provision(*_args):
        observed["thread_id"] = threading.get_ident()
        gate.wait(timeout=3)

    with patch(PROVISION, side_effect=slow_provision):
        thread = schedule_create_and_seed(
            session_id="s-nb",
            project_id="proj-wl",
            project_path=Path("/tmp/proj"),
            base_branch="main",
            seed_callback=None,
        )
        assert thread.is_alive()
        gate.set()
        thread.join(timeout=3)

    assert observed["thread_id"] != caller_id


def test_wait_for_ready_returns_immediately_when_already_ready():
    _seed_session_row("s-wr")
    set_worktree_status("s-wr", "ready")
    asyncio.run(wait_for_ready("s-wr"))


@pytest.mark.parametrize("status", ["create_failed", "seed_failed"])
def test_wait_for_ready_raises_on_failed_status(status):
    _seed_session_row("s-wr-f")
    set_worktree_status("s-wr-f", status)

    async def _run() -> None:
        with pytest.raises(WorktreeUnavailableError):
            await wait_for_ready("s-wr-f")

    asyncio.run(_run())


def test_wait_for_ready_unblocks_when_status_becomes_ready():
    _seed_session_row("s-wait")

    async def _run() -> None:
        async def flip_later():
            await asyncio.sleep(0.05)
            set_worktree_status("s-wait", "ready")
            _signal_ready("s-wait")
        asyncio.create_task(flip_later())
        await wait_for_ready("s-wait")

    asyncio.run(_run())
    assert _read_status("s-wait") == "ready"


def test_wait_for_ready_survives_lost_wakeup(monkeypatch):
    monkeypatch.setattr("hypergolic.git.worktree_lifecycle.BACKSTOP_POLL", 0.01)
    """Regression: hypergolic run creates sessions before any loop exists.

    The ready-event then registers with loop=None, and the worktree thread's
    fallback ``event.set()`` from a foreign thread never wakes a parked
    waiter. The DB-poll backstop must unblock within a poll interval.
    """


    _seed_session_row("s-lost")
    _get_or_create_event("s-lost")

    async def _run() -> None:
        waiter = asyncio.create_task(wait_for_ready("s-lost"))
        await asyncio.sleep(0.01)

        def finish() -> None:
            set_worktree_status("s-lost", "ready")
            _signal_ready("s-lost")

        threading.Thread(target=finish).start()
        await asyncio.wait_for(waiter, timeout=3)

    asyncio.run(_run())


def test_wait_for_ready_times_out_when_status_never_resolves(monkeypatch):
    monkeypatch.setattr("hypergolic.git.worktree_lifecycle.BACKSTOP_POLL", 0.01)
    _seed_session_row("s-wedged")
    set_worktree_status("s-wedged", "creating")

    async def _run() -> None:
        with pytest.raises(WorktreeUnavailableError, match="Timed out"):
            await wait_for_ready("s-wedged", timeout=0.05)

    asyncio.run(_run())


def test_run_teardown_removes_workspace_dir(tmp_path: Path):
    wt = tmp_path / "ws"
    wt.mkdir()
    (wt / "file.txt").write_text("x")
    run_teardown(worktree_path=str(wt))
    assert not wt.exists()


def test_run_teardown_none_and_missing_are_noops(tmp_path: Path):
    run_teardown(worktree_path=None)
    run_teardown(worktree_path=str(tmp_path / "ghost"))


def test_schedule_teardown_runs_on_daemon_thread_and_discards_event(tmp_path: Path):
    wt = tmp_path / "ws"
    wt.mkdir()
    _ready_events["s-td"] = (asyncio.Event(), None)
    thread = schedule_teardown(session_id="s-td", worktree_path=str(wt))
    assert thread.daemon
    thread.join(timeout=3)
    assert not wt.exists()
    assert "s-td" not in _ready_events


def test_discard_event_removes_registered_event():
    _ready_events["s-discard"] = (asyncio.Event(), None)
    _discard_event("s-discard")
    assert "s-discard" not in _ready_events

    _discard_event("s-ghost")
    assert "s-ghost" not in _ready_events
