from unittest.mock import patch

from hypergolic.dispatch import state as dispatch_state
from hypergolic.dispatch.knowledge import (
    finalize_deferred_conclude,
    maybe_dispatch_distillation,
    should_distill,
)
from hypergolic.enums import SessionStatus
from hypergolic.sessions import session_rows
from hypergolic.sessions.operations import load_session
from tests.conftest import make_message, make_project, make_session

def _row(sid: str) -> tuple[str, object]:
    row = session_rows.fetch_one(sid)
    return row.status, row.concluded_at


async def test_finalize_flips_concluding_and_broadcasts(broadcast):
    make_project()
    sid = make_session()
    session_rows.update(sid, status=SessionStatus.CONCLUDING.value)

    await finalize_deferred_conclude(sid, broadcast)

    status, concluded_at = _row(sid)
    assert status == SessionStatus.CONCLUDED.value
    assert concluded_at is not None
    assert broadcast.await_count == 1
    event = broadcast.await_args.args[0]
    assert event.type == "session_status_change"
    assert event.content[0]["status"] == "concluded"
    assert event.content[0]["concluded_at"]

    await finalize_deferred_conclude(sid, broadcast)
    assert broadcast.await_count == 1
    assert _row(sid) == (status, concluded_at)


async def test_finalize_noops_unless_concluding(broadcast):
    make_project()
    sid = make_session()

    await finalize_deferred_conclude(sid, broadcast)

    assert _row(sid)[0] != SessionStatus.CONCLUDED.value
    broadcast.assert_not_awaited()


async def test_maybe_dispatch_finalizes_when_distillation_declined(broadcast):
    make_project()
    sid = make_session()
    session_rows.update(sid, status=SessionStatus.CONCLUDING.value)

    await maybe_dispatch_distillation(load_session(sid), broadcast)

    assert _row(sid)[0] == SessionStatus.CONCLUDED.value


async def test_maybe_dispatch_finalizes_when_dispatch_raises(broadcast):
    make_project()
    sid = make_session()
    session_rows.update(sid, status=SessionStatus.CONCLUDING.value)

    with patch(
        "hypergolic.dispatch.knowledge._dispatch_distillation",
        side_effect=RuntimeError("boom"),
    ):
        await maybe_dispatch_distillation(load_session(sid), broadcast)

    assert _row(sid)[0] == SessionStatus.CONCLUDED.value


async def test_finalize_deferred_conclude_schedules_sandbox_cleanup(broadcast):
    make_project()
    sid = make_session()
    session_rows.update(sid, status=SessionStatus.CONCLUDING.value)
    with patch("hypergolic.dispatch.knowledge.schedule_session_sandbox_cleanup") as sched:
        await finalize_deferred_conclude(sid, broadcast)
    sched.assert_called_once_with(sid)
    assert _row(sid)[0] == SessionStatus.CONCLUDED.value


async def test_should_distill_gates_on_depth_and_parentage():
    make_project()
    thin = make_session()
    deep = make_session()
    for _ in range(3):
        make_message(deep, role="assistant")
    child = make_session(parent_id=deep)
    for _ in range(3):
        make_message(child, role="assistant")

    with patch.object(dispatch_state, "_turn_runner", lambda *a: None):
        assert await should_distill(load_session(deep))
        assert not await should_distill(load_session(thin))
        assert not await should_distill(load_session(child))

    with patch.object(dispatch_state, "_turn_runner", None):
        assert not await should_distill(load_session(deep))
