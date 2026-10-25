import pytest

from hypergolic.dispatch.conclude import ConcludeInput, set_concluded_at
from hypergolic.dispatch.conclude.handler import _handle_conclude
from hypergolic.sessions import session_rows
from hypergolic.dispatch.tests._conclude_helpers import (
    conclude_patches,
    make_ctx,
    make_session,
    seed,
)

def testset_concluded_at_writes_to_db():
    seed()
    result = set_concluded_at("s1")
    assert result.tzinfo is not None
    assert session_rows.fetch_one("s1").concluded_at == result


@pytest.mark.parametrize(
    "resolved, outcome, conclusion",
    [
        (True, "success", "Done"),
        (False, "failure", "Could not finish"),
    ],
)
async def test_conclude_with_parent_concludes(broadcast, resolved, outcome, conclusion):
    seed("child", parent_id="parent")
    ctx = make_ctx(make_session("child", parent_id="parent"), broadcast)
    inp = ConcludeInput(outcome=outcome, conclusion=conclusion)

    with conclude_patches(resolved=resolved) as mocks:
        output = await _handle_conclude(inp, ctx)

    assert not output.is_error
    assert outcome in output.first_text()
    mocks.status.assert_called_once()
    mocks.concluded.assert_called_once_with("child")
    if resolved:
        assert broadcast.call_count == 1
        assert broadcast.call_args[0][0].type == "dispatch_concluded"


async def test_conclude_not_resolved_no_parent_returns_error(broadcast):
    seed("orphan")
    ctx = make_ctx(make_session("orphan", parent_id=None), broadcast)
    inp = ConcludeInput(outcome="success", conclusion="Done")

    with conclude_patches(resolved=False) as mocks:
        output = await _handle_conclude(inp, ctx)

    assert output.is_error
    assert "No pending dispatch" in output.first_text()
    mocks.status.assert_not_called()


async def test_conclude_resolved_no_parent_no_dispatch_concluded_event(broadcast):
    seed("orphan")
    ctx = make_ctx(make_session("orphan", parent_id=None), broadcast)
    inp = ConcludeInput(outcome="success", conclusion="Done")

    with conclude_patches(resolved=True):
        output = await _handle_conclude(inp, ctx)

    assert not output.is_error
    broadcast.assert_not_called()
