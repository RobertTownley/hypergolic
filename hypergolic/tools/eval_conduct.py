from __future__ import annotations

import logging
from typing import Any

from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.eval_behavior import EvalBehavior
from hypergolic.harness.primitives.tool import Tool
from hypergolic.schemas import Session

logger = logging.getLogger(__name__)

_DENY = "DENY"
_DELEGATE = "DELEGATE"


def is_conducted(session: Session) -> bool:
    return session.conducted_by is not None


async def eval_behavior(tool: Tool, parsed: Any, session: Session) -> EvalBehavior:
    if tool.eval_behavior is None or not is_conducted(session):
        return EvalBehavior.EXECUTE
    try:
        return EvalBehavior(await tool.eval_behavior(ApprovalContext(input=parsed, session=session)))
    except Exception:
        logger.warning(
            "eval_behavior for '%s' raised; defaulting to CONDUCT", tool.id, exc_info=True,
        )
        return EvalBehavior.CONDUCT


async def is_conducted_call(tool: Tool, parsed: Any, session: Session) -> bool:
    return await eval_behavior(tool, parsed, session) == EvalBehavior.CONDUCT


def conduct_decision(decision: ToolApprovalDecision, conducted: bool) -> ToolApprovalDecision:
    if not conducted or decision.decision == _DENY:
        return decision
    return ToolApprovalDecision(decision=_DELEGATE, reason=decision.reason)
