from __future__ import annotations

from enum import StrEnum
from typing import Awaitable, Callable

from hypergolic.harness.primitives.approval import ApprovalContext


class EvalBehavior(StrEnum):
    EXECUTE = "execute"
    CONDUCT = "conduct"


EvalBehaviorFn = Callable[[ApprovalContext], Awaitable[EvalBehavior]]


async def always_conduct(_ctx: ApprovalContext) -> EvalBehavior:
    return EvalBehavior.CONDUCT
