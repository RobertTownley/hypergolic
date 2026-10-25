from types import SimpleNamespace
from typing import Any, cast

from hypergolic.contrib.tools.git_sync import git_fetch_tool
from hypergolic.contrib.tools.history import history_tool
from hypergolic.contrib.tools.pull_request import pull_request_tool
from hypergolic.contrib.tools.mcp_command.actions import mcp_eval_behavior
from hypergolic.contrib.tools.mcp_command.parse import McpInput
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.eval_behavior import EvalBehavior, always_conduct
from hypergolic.harness.primitives.tool import Tool
from hypergolic.schemas import Session
from hypergolic.tools import approval_delegate
from hypergolic.tools.approval import ApprovalRequest
from hypergolic.tools.eval_conduct import conduct_decision, is_conducted_call

CHILD = "child1"


def _session(conducted_by: str | None = None) -> Session:
    return cast(Session, SimpleNamespace(id=CHILD, conducted_by=conducted_by))


async def _run(*_: Any) -> None:
    return None


def _tool(eval_behavior: Any = None) -> Tool:
    return Tool(id="t", name="T", description="d", run=_run, eval_behavior=eval_behavior)


async def test_conduct_only_in_a_conducted_session():
    tool = _tool(always_conduct)
    assert not await is_conducted_call(tool, None, _session())
    assert await is_conducted_call(tool, None, _session("parent"))


async def test_unset_means_execute():
    assert not await is_conducted_call(_tool(), None, _session("parent"))


async def test_a_raising_callback_conducts():
    async def boom(_ctx: ApprovalContext) -> EvalBehavior:
        raise RuntimeError("bug")

    assert await is_conducted_call(_tool(boom), None, _session("parent"))


def test_conduct_turns_allow_into_delegate_but_deny_stands():
    allow = ToolApprovalDecision(decision="ALLOW")
    deny = ToolApprovalDecision(decision="DENY", reason="no")
    assert conduct_decision(allow, True).decision == "DELEGATE"
    assert conduct_decision(allow, False).decision == "ALLOW"
    assert conduct_decision(deny, True) == deny


async def test_mcp_exec_is_conducted_but_listing_is_not():
    session = _session()
    exec_ctx = ApprovalContext(input=McpInput(action="exec", server="docs", tool="search"), session=session)
    list_ctx = ApprovalContext(input=McpInput(action="list"), session=session)
    assert await mcp_eval_behavior(exec_ctx) == EvalBehavior.CONDUCT
    assert await mcp_eval_behavior(list_ctx) == EvalBehavior.EXECUTE


def test_history_pull_request_and_git_fetch_are_conducted():
    assert history_tool.eval_behavior is always_conduct
    assert git_fetch_tool.eval_behavior is always_conduct
    assert pull_request_tool.eval_behavior is always_conduct


def test_describe_asks_the_conductor_for_a_mock():
    req = ApprovalRequest(
        request_id="r1", tool_name="mcp.docs.search", tool_input={}, session_id=CHILD,
        delegated=True, conducted=True,
    )
    pending = approval_delegate.PendingApproval(
        request=req, child_id=CHILD, parent_may_approve=False, future=cast(Any, None),
    )
    assert "made-up IDs" in approval_delegate.describe(pending)
