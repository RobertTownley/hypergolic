from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel

from hypergolic.schemas import Session


ApprovalDecision = Literal["ALLOW", "DENY", "REQUIRE_APPROVAL", "DELEGATE"]


class ToolApprovalDecision(BaseModel):
    decision: ApprovalDecision
    reason: str | None = None
    context: str | None = None


@dataclass
class MCPApprovalContext:
    """Context passed to an MCP approval policy.

    ``server`` and ``tool`` identify the specific MCP call; ``input`` is the
    raw dict the agent passed; ``session`` carries the usual runtime state
    (project_id, worktree, etc.).
    """

    server: str
    tool: str
    input: dict
    session: Session


@dataclass
class ApprovalContext:
    """Context passed to approval callables.

    Contains everything an approval function needs to make a decision:
    the parsed input and the session it was invoked in.
    """

    input: Any
    session: Any  # hypergolic.schemas.Session (avoid circular import)


ApprovalPolicy = Callable[[ApprovalContext], ToolApprovalDecision]


class TotalPolicy:
    """One decision for every input.

    A distinct type rather than a closure so a caller can *recognize* totality:
    documentation may state the posture of a total policy up front, while an
    arbitrary callable has to be invoked with real arguments to know anything.
    """

    def __init__(self, decision: ApprovalDecision, reason: str | None = None) -> None:
        self.decision = decision
        self.reason = reason

    def __call__(self, _ctx: ApprovalContext) -> ToolApprovalDecision:
        return ToolApprovalDecision(decision=self.decision, reason=self.reason)

    def __repr__(self) -> str:
        return f"always({self.decision!r})" if not self.reason else (
            f"always({self.decision!r}, {self.reason!r})"
        )


def always(decision: ApprovalDecision, reason: str | None = None) -> ApprovalPolicy:
    """The trivial total policy: one decision for every input.

    Approval policies are callables rather than ``Callable | str`` so there is a
    single code path deciding a command's posture, and so an agent reading
    ``/tools/<name>/source`` can predict exactly what will block on a human.
    """
    return TotalPolicy(decision, reason)
