from __future__ import annotations

from hypergolic.enums import SessionStatus
from hypergolic.sessions import session_rows
from hypergolic.sessions.resume import claim_resumable_sessions, set_session_resume
from tests.conftest import make_project, make_message, make_session

def _flag(session_id: str) -> bool:
    return session_rows.fetch_one(session_id).resume_pending


def _resumable_session(sid: str, parent_id: str | None = None) -> str:
    session = make_session(sid=sid, parent_id=parent_id, role="reviewer" if parent_id else "generalist")
    make_message(
        session,
        role="assistant",
        content=[{"type": "tool_use", "id": f"tu-{sid}", "name": "cmd", "input": {}}],
    )
    return session


def test_mark_and_claim_round_trip():
    make_project("proj-1")
    session = _resumable_session("s-1")

    set_session_resume(session, True)
    assert _flag(session) is True

    assert claim_resumable_sessions() == [session]
    assert _flag(session) is False


def test_claim_skips_children_and_settled_sessions():
    make_project("proj-1")
    parent = _resumable_session("parent-1")
    child = _resumable_session("child-1", parent_id=parent)
    concluded = _resumable_session("s-done")
    interrupted = _resumable_session("s-int")
    session_rows.update(concluded, status=SessionStatus.CONCLUDED.value)
    session_rows.update(interrupted, status=SessionStatus.INTERRUPTED.value)
    for sid in (parent, child, concluded, interrupted):
        set_session_resume(sid, True)

    assert claim_resumable_sessions() == [parent]
    for sid in (child, concluded, interrupted):
        assert _flag(sid) is False


def test_claim_ignores_unflagged_sessions():
    make_project("proj-1")
    _resumable_session("s-1")

    assert claim_resumable_sessions() == []


def test_claim_skips_a_transcript_that_would_be_sent_as_prefill():
    make_project("proj-1")
    settled = make_session(sid="s-settled")
    make_message(settled, role="assistant", text="done")
    set_session_resume(settled, True)

    assert claim_resumable_sessions() == []


def test_claim_resumes_a_turn_the_model_had_not_finished():
    make_project("proj-1")
    session = _resumable_session("s-tool")
    set_session_resume(session, True)

    assert claim_resumable_sessions() == [session]
