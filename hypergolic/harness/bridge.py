"""Tool invocation + approval helpers shared by the engine.

Tools are a single unified type (:class:`hypergolic.harness.primitives.Tool`),
authored the same way whether they ship with the standard library or come from
a user's config. This module holds the glue the engine uses to actually run a
tool's ``run`` callable and to evaluate its approval policy.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.harness.primitives.validation import ValidationResult

logger = logging.getLogger(__name__)


def _param_count(fn: Any) -> int:
    sig = inspect.signature(fn)
    return len([p for p in sig.parameters.values() if p.name != "self"])


async def call_handler(tool: Tool, parsed_input: Any, ctx: ToolContext) -> Any:
    """Run a tool's ``run`` callable, tolerating 1-arg (ctx-only) signatures.

    Exceptions propagate: callers differ on how a failure should be reported.
    """
    run_fn = tool.run
    assert run_fn is not None, f"Tool '{tool.id}' has no run callable"
    if _param_count(run_fn) >= 2:
        return await run_fn(parsed_input, ctx)
    return await run_fn(ctx)


async def invoke_tool(tool: Tool, parsed_input: Any, ctx: ToolContext) -> ToolResult:
    """Run a tool and report a failure as an error :class:`ToolResult`."""
    try:
        return await call_handler(tool, parsed_input, ctx)
    except Exception as e:
        logger.error("Tool '%s' failed: %s", tool.id, e, exc_info=True)
        return ToolResult.text(f"Error with tool call: {e}", is_error=True)


async def run_tool_call_validation(tool: Tool, parsed_input: Any, ctx: ToolContext) -> ValidationResult:
    if tool.validate_tool_call is None:
        return ValidationResult.valid()
    try:
        result = await tool.validate_tool_call(parsed_input, ctx)
    except Exception as e:
        logger.error("Validation for tool '%s' failed: %s", tool.id, e, exc_info=True)
        return ValidationResult.invalid(f"Validation error: {e}")
    if not isinstance(result, ValidationResult):
        return ValidationResult.invalid(f"Validation error: {tool.id} returned {type(result).__name__}, not ValidationResult")
    return result


def evaluate_harness_approval(
    tool: Tool,
    raw_input: dict[str, Any],
    session: Any | None = None,
) -> ToolApprovalDecision:
    approval = tool.approval_policy

    try:
        parsed_input = None
        if tool.input_schema:
            parsed_input = tool.input_schema.model_validate(raw_input)

        ctx = ApprovalContext(input=parsed_input, session=session)
        return approval(ctx)
    except Exception:
        logger.warning(
            "Approval callback for tool '%s' raised an exception; defaulting to REQUIRE_APPROVAL",
            tool.id,
            exc_info=True,
        )
        return ToolApprovalDecision(decision="REQUIRE_APPROVAL")

