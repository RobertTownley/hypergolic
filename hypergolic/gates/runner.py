"""Executing a land request's gate pipeline.

Each gate evaluates the merge candidate (the pushed tree squashed onto the
base tip, built by :mod:`hypergolic.gates.candidate`) and reports one verdict
line for the push output. Failure short-circuits; :class:`Parallel` children
run concurrently. Every gate is stateless and re-runnable — a killed push
mid-gate leaves nothing to clean up.
"""

from __future__ import annotations

import asyncio

from hypergolic.gates.check import run_check
from hypergolic.gates.model import AgenticReview, Check, Gate, Parallel, UserApproval
from hypergolic.gates.request import GateVerdict, LandRequest
from hypergolic.gates.review import run_agentic_review
from hypergolic.gates.user_approval import run_user_approval


async def run_pipeline(gates: list[Gate], req: LandRequest) -> GateVerdict:
    lines: list[str] = []
    for gate in gates:
        verdict = await _run_gate(gate, req)
        lines += verdict.lines
        if not verdict.ok:
            return GateVerdict(ok=False, lines=lines)
    return GateVerdict(ok=True, lines=lines)


async def _run_gate(gate: Gate, req: LandRequest) -> GateVerdict:
    if isinstance(gate, Parallel):
        results = await asyncio.gather(*(_run_gate(g, req) for g in gate.gates))
        lines = [line for r in results for line in r.lines]
        return GateVerdict(ok=all(r.ok for r in results), lines=lines)
    if isinstance(gate, Check):
        return await run_check(gate, req)
    if isinstance(gate, AgenticReview):
        return await run_agentic_review(gate, req)
    assert isinstance(gate, UserApproval)
    return await run_user_approval(req)
