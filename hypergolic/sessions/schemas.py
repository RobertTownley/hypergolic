from typing import Any

from pydantic import BaseModel, Field

from hypergolic.enums import ModelTier, SessionStatus


class CreateSessionRequest(BaseModel):
    model_tier: ModelTier | None = Field(default=None)
    project_id: str
    role: str = "generalist"
    base_branch: str = Field(
        description="Branch to root the session's worktree on. Required.",
    )


class ForkSessionRequest(BaseModel):
    with_workspace: bool = False


class ConcludePreview(BaseModel):
    is_worktree_session: bool
    branch_has_unmerged_commits: bool = False
    unmerged_count: int = 0


class SessionResponse(BaseModel):
    id: str
    model_tier: ModelTier
    project_id: str
    project_name: str
    role: str
    status: SessionStatus = SessionStatus.IDLE
    created_at: str
    updated_at: str
    message_count: int = 0
    workflow_id: str | None = None
    workflow_name: str | None = None
    workflow_state_id: str | None = None
    workflow_state_name: str | None = None
    parent_id: str | None = None
    description: str | None = None
    conclusion_rating: int | None = None
    conclusion_feedback: str | None = None
    concluded_at: str | None = None
    worktree_path: str | None = None
    worktree_branch: str | None = None
    base_branch: str | None = None
    worktree_status: str | None = None
    context: "SessionContextResponse | None" = None


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: list[Any]
    model: str | None = None
    stop_reason: str | None = None
    usage: dict[str, Any] | None = None
    truncated: bool = False
    created_at: str


class ToolInfo(BaseModel):
    id: str
    name: str
    description: str
    reason: str
    requires_approval: bool
    token_estimate: int
    mcp_server: str | None = None
    input_schema: dict | None = None
    usage: str | None = None


class PromptPartInfo(BaseModel):
    source: str
    content: str
    token_estimate: int


class RoleInfo(BaseModel):
    id: str
    name: str
    source: str


class SkillInfo(BaseModel):
    id: str
    name: str
    description: str
    source: str


class SkillsSummary(BaseModel):
    total: int
    #: Skill ids this session has `activate_skill`ed, in first-activation order.
    activated: list[str] = []


class SessionSearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    max_results: int = 20


class SessionSearchMatch(BaseModel):
    session_id: str
    project_id: str
    project_name: str
    model_tier: str
    created_at: str
    updated_at: str
    message_count: int
    match_text: str
    match_role: str
    first_message: str | None = None


class SessionSearchResponse(BaseModel):
    matches: list[SessionSearchMatch]


class SessionContextResponse(BaseModel):
    tools: list[ToolInfo]
    tools_count: int
    tools_token_estimate: int
    skills_summary: SkillsSummary
    mcp_enabled: list[str]
    prompt_token_estimate: int
