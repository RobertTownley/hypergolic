from __future__ import annotations

import pytest

from hypergolic.enums import SessionStatus
from hypergolic.sessions import recovery, session_rows
from hypergolic.sessions.recovery import recover_in_flight_sessions, recover_stranded_worktrees
from tests.conftest import make_project, make_session

pytestmark = pytest.mark.db


def test_recover_idles_top_level_and_interrupts_children():
    make_project("proj-1")
    parent = make_session(sid="parent-1")
    child = make_session(sid="child-1", parent_id=parent, role="reviewer")
    session_rows.update(parent, status=SessionStatus.TOOL_USE.value)
    session_rows.update(child, status=SessionStatus.STREAMING.value)

    assert recover_in_flight_sessions() == 2
    assert session_rows.fetch_one(parent).status == SessionStatus.IDLE.value
    assert session_rows.fetch_one(child).status == SessionStatus.INTERRUPTED.value
    assert session_rows.fetch_one(parent).resume_pending is True
    assert session_rows.fetch_one(child).resume_pending is False


def test_recover_ignores_settled_sessions():
    make_project("proj-1")
    idle = make_session(sid="s-idle")
    concluded = make_session(sid="s-done")
    interrupted = make_session(sid="s-int", parent_id=idle)
    session_rows.update(concluded, status=SessionStatus.CONCLUDED.value)
    session_rows.update(interrupted, status=SessionStatus.INTERRUPTED.value)

    assert recover_in_flight_sessions() == 0
    assert session_rows.fetch_one(idle).status == SessionStatus.IDLE.value
    assert session_rows.fetch_one(concluded).status == SessionStatus.CONCLUDED.value
    assert session_rows.fetch_one(interrupted).status == SessionStatus.INTERRUPTED.value


def test_recover_covers_every_in_flight_status():
    make_project("proj-1")
    statuses = [
        SessionStatus.THINKING,
        SessionStatus.STREAMING,
        SessionStatus.TOOL_USE,
        SessionStatus.TRUNCATING,
        SessionStatus.AWAITING_APPROVAL,
    ]
    for i, status in enumerate(statuses):
        session_rows.update(make_session(sid=f"s-{i}"), status=status.value)

    assert recover_in_flight_sessions() == len(statuses)
    for i in range(len(statuses)):
        assert session_rows.fetch_one(f"s-{i}").status == SessionStatus.IDLE.value


def test_recover_skips_resume_for_cli_sessions():
    make_project("proj-1")
    cli = make_session(sid="cli-1", origin="cli")
    session_rows.update(cli, status=SessionStatus.STREAMING.value)

    assert recover_in_flight_sessions() == 1
    assert session_rows.fetch_one(cli).status == SessionStatus.IDLE.value
    assert session_rows.fetch_one(cli).resume_pending is False


def test_recover_reschedules_stranded_worktrees(tmp_path, monkeypatch):
    make_project("proj-1")
    scheduled: list[str] = []
    monkeypatch.setattr(
        recovery, "schedule_create_and_seed",
        lambda **kw: scheduled.append(kw["session_id"]),
    )
    partial = tmp_path / "wt"
    (partial / "sub").mkdir(parents=True)
    (partial / "file").write_text("x")
    stuck = make_session(sid="wt-cloning", worktree_status="cloning", worktree_path=str(partial))
    make_session(sid="wt-ready", worktree_status="ready")
    make_session(sid="wt-failed", worktree_status="create_failed")
    done = make_session(sid="wt-concluded", worktree_status="seeding")
    session_rows.update(done, status=SessionStatus.CONCLUDED.value)
    orphan = make_session(sid="wt-orphan", project_id="gone", worktree_status="pending")

    assert recover_stranded_worktrees() == 2
    assert scheduled == [stuck]
    assert partial.is_dir() and not any(partial.iterdir())
    assert session_rows.fetch_one(orphan).worktree_status == "create_failed"


def test_recovery_sweeps_stuck_concluding():
    make_project()
    sid = make_session()
    session_rows.update(sid, status=SessionStatus.CONCLUDING.value)

    assert recover_in_flight_sessions() == 1
    row = session_rows.fetch_one(sid)
    assert row.status == SessionStatus.CONCLUDED.value and row.concluded_at is not None
