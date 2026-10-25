import logging
from typing import Any

from hypergolic.db import audit_rows
from hypergolic.db.models import DBToolApproval
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.ids import new_id
from hypergolic.tools.approval import AnnotationItem, ApprovalResponse

logger = logging.getLogger(__name__)


def format_denial(response: ApprovalResponse) -> str:
    denial_text = "User denied tool call."
    if response.denial_reason:
        denial_text += f" Reason: {response.denial_reason}"
    if response.annotations:
        denial_text += "\n\nUser annotations:\n"
        for ann in response.annotations:
            denial_text += f'- "{ann.highlighted_text}": {ann.comment}\n'
    return denial_text


def append_annotations(output: ToolResult, annotations: list[AnnotationItem]) -> ToolResult:
    annotation_text = "\n\nUser feedback on this artifact:\n"
    for ann in annotations:
        annotation_text += f'- "{ann.highlighted_text}": {ann.comment}\n'
    return output.append_text(annotation_text)


def record_approval(
    session_id: str,
    tool_use_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    response: ApprovalResponse,
) -> None:
    try:
        audit_rows.insert(DBToolApproval(
            id=new_id(),
            session_id=session_id,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            tool_input=tool_input,
            approved=response.approved,
            denial_reason=(
                "mocked by parent session" if response.mock_result is not None
                else response.denial_reason
            ),
            annotations=[
                {"highlighted_text": a.highlighted_text, "comment": a.comment}
                for a in response.annotations
            ] if response.annotations else None,
        ))
    except Exception:
        logger.exception("Failed to record tool approval for tool_use_id=%s", tool_use_id)
