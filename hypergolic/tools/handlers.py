"""Core tool-use handling: execute tools and process an agent message."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from anthropic.types import MessageParam, ToolResultBlockParam, ToolUseBlock
from anthropic.types.message import Message

from hypergolic.messages.types import BroadcastFn
from hypergolic.schemas import Session
from hypergolic.tools.approval import (  # noqa: F401 — re-exported
    AnnotationItem,
    ApprovalCallback,
    ApprovalRequest,
    ApprovalResponse,
    build_resolved_view,
    resolve_approval_decision,
)
from hypergolic.tools.approval_outcome import append_annotations, format_denial, record_approval
from hypergolic.harness.bridge import invoke_tool, run_tool_call_validation
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.harness.primitives.validation import ValidationResult
from hypergolic.tools.approval_view import ResolvedView
from hypergolic.tools.eval_conduct import conduct_decision, is_conducted_call
from hypergolic.tools.guaranteed_output import append_pending
from hypergolic.tools.output_shaping import shape_tool_output
from hypergolic.tools.truncation import result_block, truncate_tool_output
from hypergolic.tools.approval_view import shell_presentation
from hypergolic.telemetry.tracing import tracer
from hypergolic.git.worktree_lifecycle import WorktreeUnavailableError, wait_for_ready

logger = logging.getLogger(__name__)

# Re-export public types so existing imports keep working.
__all__ = [
    "AnnotationItem",
    "ApprovalCallback",
    "ApprovalRequest",
    "ApprovalResponse",
    "ToolUseResult",
    "handle_tool_use",
]

_DENY = "DENY"
_REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
_DELEGATE = "DELEGATE"


@dataclass
class ToolUseResult:
    message: MessageParam


def _approval_presentation(
    tool: Tool, tool_input: dict[str, Any]
) -> tuple[str, "ResolvedView | None"]:
    """Pick the name and view the approval UI should show.

    Every call arrives through the one `cmd` tool, so the generic presentation
    would say "Command" and dump the raw input. Show the shell line instead.
    """
    if tool.id == "cmd":

        resolved = shell_presentation(tool_input)
        if resolved is not None:
            return resolved
    return tool.name, build_resolved_view(tool, tool_input)


async def _execute_tool(tool: Tool, parsed_input: Any, ctx: ToolContext) -> ToolResult:
    """Call the tool with an already-validated input model, returning an error ToolResult on failure."""
    attributes = {"session.id": ctx.session.id, "tool.id": tool.id}
    with tracer.start_as_current_span(f"tool {tool.id}", attributes=attributes):
        return await invoke_tool(tool, parsed_input, ctx)


async def _process_single_tool(
    content: ToolUseBlock,
    tool_map: dict[str, Tool],
    session: Session,
    broadcast: BroadcastFn,
    approval_callback: ApprovalCallback | None,
) -> ToolResultBlockParam:
    tool = tool_map.get(content.name)
    if tool is None:
        logger.error(
            "Tool '%s' not found in tool_map (available: %s)",
            content.name, list(tool_map.keys()),
        )
        block = ToolResultBlockParam(
            tool_use_id=content.id,
            type="tool_result",
            content=(
                f"Tool '{content.name}' is not available. Only `cmd` ships over "
                "the wire; every other capability is a command on PATH in the "
                "sandbox \u2014 see /tools/index.md."
            ),
            is_error=True,
        )
        return block

    tool_input: dict = content.input  # type: ignore[assignment]

    parsed_input: Any = None
    if tool.input_schema is not None:
        try:
            parsed_input = tool.input_schema.model_validate(tool_input)
        except Exception as e:
            return result_block(content.id, ToolResult.text(f"Invalid tool input: {e}", is_error=True))

    if tool.requires_worktree:
        try:
            await wait_for_ready(session.id)
        except WorktreeUnavailableError as err:
            return result_block(
                content.id,
                ToolResult.text(
                    f"Tool '{content.name}' requires a ready worktree, but it is unavailable: {err}",
                    is_error=True,
                ),
            )

    ctx = ToolContext(session=session, broadcast=broadcast, tool_id=tool.id, tool_use_id=content.id)
    conducted = await is_conducted_call(tool, parsed_input, session)
    validation = (
        ValidationResult.valid() if conducted
        else await run_tool_call_validation(tool, parsed_input, ctx)
    )
    if not validation.is_valid:
        return result_block(content.id, ToolResult.text(validation.message or "", is_error=True))

    approval_decision = conduct_decision(
        resolve_approval_decision(tool, tool_input, session), conducted,
    )

    if approval_decision.decision == _DENY:
        reason = approval_decision.reason or "Tool call denied by approval rule."
        return result_block(content.id, ToolResult.text(reason, is_error=True))

    approved_annotations: list[AnnotationItem] | None = None
    if approval_decision.decision in (_REQUIRE_APPROVAL, _DELEGATE) and approval_callback:
        display_name, view = _approval_presentation(tool, tool_input)
        request = ApprovalRequest(
            request_id=content.id,
            tool_name=content.name,
            tool_input=tool_input,
            session_id=session.id,
            approval_view=view,
            tool_display_name=display_name,
            delegated=approval_decision.decision == _DELEGATE,
            conducted=conducted,
        )
        response = await approval_callback(request)
        await asyncio.to_thread(
            record_approval,
            session_id=session.id,
            tool_use_id=content.id,
            tool_name=content.name,
            tool_input=tool_input,
            response=response,
        )

        if response.mock_result is not None:
            return result_block(
                content.id, ToolResult.text(response.mock_result, is_error=response.mock_is_error),
            )
        if not response.approved:
            return result_block(
                content.id,
                ToolResult.text(format_denial(response), is_error=True),
            )

        approved_annotations = response.annotations

    output = await _execute_tool(tool, parsed_input, ctx)
    if validation.message:
        output = output.append_text(validation.message)

    output = truncate_tool_output(shape_tool_output(output))
    output = append_pending(output, session.id)

    if approved_annotations and not output.is_error:
        output = append_annotations(output, approved_annotations)

    return result_block(content.id, output)


async def handle_tool_use(
    agent_message: Message,
    tools: list[Tool],
    session: Session,
    broadcast: BroadcastFn,
    approval_callback: ApprovalCallback | None = None,
) -> ToolUseResult:
    """Process all tool-use blocks in *agent_message* and return results."""
    tool_map = {tool.id: tool for tool in tools}

    tool_use_blocks = [
        block for block in agent_message.content
        if isinstance(block, ToolUseBlock)
    ]

    tool_result_blocks: list[ToolResultBlockParam] = list(await asyncio.gather(*[
        _process_single_tool(block, tool_map, session, broadcast, approval_callback)
        for block in tool_use_blocks
    ]))

    return ToolUseResult(
        message=MessageParam(role="user", content=tool_result_blocks),
    )
