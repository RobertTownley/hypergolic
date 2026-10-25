from typing import Any, Literal

from pydantic import BaseModel, Field

from hypergolic.enums import ModelTier


class ConnectMessage(BaseModel):
    type: Literal["chat"] = "chat"
    message: str = Field(..., min_length=1)
    model_tier: ModelTier | None = Field(default=None)
    session_id: str | None = None
    project_id: str | None = None
    base_branch: str | None = Field(
        default=None,
        description=(
            "Required when creating a new session via this message "
            "(i.e. when `session_id` is omitted). Ignored otherwise."
        ),
    )
    content_blocks: list[dict[str, Any]] | None = None
    workflow_id: str | None = None


class AnnotationPayload(BaseModel):
    highlighted_text: str
    comment: str


class ApprovalResponseMessage(BaseModel):
    type: Literal["tool_approval_response"] = "tool_approval_response"
    tool_use_id: str
    approved: bool
    denial_reason: str | None = None
    annotations: list[AnnotationPayload] | None = None


class ConcludeSessionMessage(BaseModel):
    type: Literal["conclude_session"] = "conclude_session"
    session_id: str
    rating: int = Field(..., ge=1, le=5)
    feedback: str | None = None
    delete_worktree: bool = Field(
        default=True,
        description=(
            "Remove the worktree directory on conclude. When True, the "
            "worktree must be clean or conclude will refuse and the UI "
            "gets a `conclude_error` back."
        ),
    )
    delete_branch: bool = Field(
        default=True,
        description=(
            "Delete the session's branch on conclude. Ignored (branch "
            "is dropped regardless) when the branch has no commits past "
            "base. When the branch has commits, True deletes it and "
            "False preserves it."
        ),
    )
    analyze_learnings: bool = Field(
        default=False,
        description=(
            "Dispatch a knowledge-distillation child to analyze the "
            "session's learnings after conclude."
        ),
    )


WsClientMessage = ConnectMessage | ApprovalResponseMessage | ConcludeSessionMessage


def parse_client_message(raw: dict[str, Any]) -> WsClientMessage:
    msg_type = raw.get("type", "chat")
    if msg_type == "tool_approval_response":
        return ApprovalResponseMessage.model_validate(raw)
    if msg_type == "conclude_session":
        return ConcludeSessionMessage.model_validate(raw)
    return ConnectMessage.model_validate(raw)
