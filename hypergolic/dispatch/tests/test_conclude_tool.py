import pytest

from hypergolic.dispatch.conclude import (
    ConcludeInput,
)
from hypergolic.dispatch.conclude.handler import _handle_conclude  # noqa: E402
from hypergolic.dispatch.tests._conclude_helpers import (
    conclude_patches,
    make_ctx,
    make_session,
    seed,
)


async def test_conclude_child_branch_always_preserved(broadcast):
    seed("child-bp", parent_id="parent-bp")
    ctx = make_ctx(make_session("child-bp", parent_id="parent-bp"), broadcast)
    inp = ConcludeInput(outcome="success", conclusion="Done", merge_ready=True)

    with conclude_patches(resolved=True, teardown_branch="branch-x") as mocks:
        output = await _handle_conclude(inp, ctx)

    assert not output.is_error
    assert mocks.teardown.call_args[1]["delete_branch_flag"] is False
    result = mocks.resolve.call_args[0][1]
    assert result.worktree_branch == "branch-x"
    assert result.merge_ready is True


@pytest.mark.parametrize(
    "resolved, outcome, conclusion",
    [
        (True, "success", "Done"),
        (False, "failure", "Couldn't finish"),
    ],
)
async def test_conclude_schedules_sandbox_cleanup(broadcast, resolved, outcome, conclusion):
    sid, pid = f"child-cl-{resolved}", f"parent-cl-{resolved}"
    seed(sid, parent_id=pid)
    ctx = make_ctx(make_session(sid, parent_id=pid), broadcast)
    inp = ConcludeInput(outcome=outcome, conclusion=conclusion)

    with conclude_patches(resolved=resolved) as mocks:
        output = await _handle_conclude(inp, ctx)

    assert not output.is_error
    mocks.cleanup.assert_called_once_with(ctx.session.id)
