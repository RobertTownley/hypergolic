import asyncio

import pytest

from hypergolic.dispatch import runner
from hypergolic.dispatch.state import DispatchResult, _child_to_parent, _pending_dispatches, resolve_dispatch
from hypergolic.tools import approval_delegate
from hypergolic.tools.approval import ApprovalRequest, ApprovalResponse

CHILD = "child-1"
PARENT = "parent-1"
BRANCH = "parent-live"


def _req(branch: str = BRANCH, repo: str = "app", tool: str = "land", rid: str = "r1") -> ApprovalRequest:
    return ApprovalRequest(
        request_id=rid, tool_name=tool, session_id=CHILD, delegated=True,
        tool_input={"arguments": {"repo": repo, "branch": branch, "sha": "a" * 40}},
    )


class Human:
    def __init__(self) -> None:
        self.asked: list[ApprovalRequest] = []

    async def __call__(self, req: ApprovalRequest) -> ApprovalResponse:
        self.asked.append(req)
        return ApprovalResponse(approved=False, denial_reason="human says no")


@pytest.fixture(autouse=True)
def _clean():
    yield
    approval_delegate.close(CHILD)
    _pending_dispatches.pop(CHILD, None)
    _child_to_parent.pop(CHILD, None)


# ── agent parent inbox ───────────────────────────────────────────


async def _pending(req: ApprovalRequest, human: Human):
    inbox = approval_delegate.open_inbox(CHILD, BRANCH)
    _child_to_parent[CHILD] = PARENT
    task = asyncio.ensure_future(approval_delegate.ask(req, human))
    pending = await inbox.get()
    return task, pending


async def test_parent_approves_a_merge_into_its_branch():
    task, pending = await _pending(_req(), Human())
    assert pending.parent_may_approve
    assert approval_delegate.answer("r1", PARENT, "approve", "looks good") is None
    response = await task
    assert response.approved and response.annotations[0].comment == "looks good"
    assert response.annotations[0].highlighted_text == ""  # reads like a user note, no parent label


@pytest.mark.parametrize("req", [_req(branch="main"), _req(repo="harness"), _req(tool="host_cmd")])
async def test_parent_cannot_approve_anything_else(req):
    task, pending = await _pending(req, Human())
    assert not pending.parent_may_approve
    assert "only the user" in (approval_delegate.answer("r1", PARENT, "approve") or "")
    assert approval_delegate.answer("r1", PARENT, "deny", "not now") is None
    response = await task
    assert not response.approved and response.denial_reason == "not now"


async def test_escalate_asks_the_human():
    human = Human()
    task, _ = await _pending(_req(tool="host_cmd"), human)
    assert approval_delegate.answer("r1", PARENT, "escalate") is None
    assert (await task).denial_reason == "human says no"
    assert len(human.asked) == 1


async def test_mock_answers_without_running_the_call():
    human = Human()
    task, pending = await _pending(_req(tool="wiki-create-pages"), human)
    assert "mock" in approval_delegate.describe(pending)
    assert approval_delegate.answer("r1", PARENT, "mock", result='{"id": "p1"}') is None
    response = await task
    assert not response.approved and response.mock_result == '{"id": "p1"}'
    assert not response.mock_is_error and human.asked == []


async def test_mock_can_be_a_failure():
    task, _ = await _pending(_req(tool="publish"), Human())
    assert approval_delegate.answer("r1", PARENT, "mock", result="boom", result_is_error=True) is None
    assert (await task).mock_is_error


async def test_mock_needs_a_result():
    task, _ = await _pending(_req(tool="publish"), Human())
    assert "--result" in (approval_delegate.answer("r1", PARENT, "mock") or "")
    approval_delegate.close(CHILD)
    await task


async def test_a_merge_gate_cannot_be_mocked():
    task, pending = await _pending(_req(), Human())
    assert "mock" not in approval_delegate.describe(pending).split("Answer with:")[1].split("\n")[0]
    assert "cannot be mocked" in (approval_delegate.answer("r1", PARENT, "mock", result="ok") or "")
    approval_delegate.close(CHILD)
    await task


async def test_only_the_childs_parent_can_answer():
    task, _ = await _pending(_req(), Human())
    assert "not from one of your children" in (approval_delegate.answer("r1", "someone-else", "approve") or "")
    approval_delegate.close(CHILD)
    assert not (await task).approved


async def test_close_denies_what_still_waits():
    task, _ = await _pending(_req(), Human())
    approval_delegate.close(CHILD)
    response = await task
    assert not response.approved and response.denial_reason == approval_delegate.NO_PARENT
    assert not approval_delegate.can_delegate(CHILD)


async def test_ask_without_a_parent_is_denied():
    human = Human()
    response = await approval_delegate.ask(_req(), human)
    assert not response.approved and human.asked == []


# ── dispatch returns early, resume waits again ───────────────────


async def test_wait_on_child_returns_for_an_approval_then_for_the_conclusion():
    loop = asyncio.get_running_loop()
    _pending_dispatches[CHILD] = loop.create_future()
    _child_to_parent[CHILD] = PARENT
    approval_delegate.open_inbox(CHILD, BRANCH)

    asking = asyncio.ensure_future(approval_delegate.ask(_req(), Human()))
    first = await runner.wait_on_child(CHILD)
    assert first.outcome == "awaiting_approval"
    assert "dispatch --resume r1" in first.conclusion
    assert CHILD in _pending_dispatches

    assert approval_delegate.answer("r1", PARENT, "approve") is None
    assert (await asyncio.wait_for(asking, 1)).approved
    resolve_dispatch(CHILD, DispatchResult(outcome="success", conclusion="done"))
    second = await runner.wait_on_child(CHILD)
    assert second.outcome == "success" and second.child_session_id == CHILD
    assert not approval_delegate.can_delegate(CHILD)
