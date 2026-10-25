from typing import Any

from pydantic import BaseModel


class WorkflowToolDetail(BaseModel):
    id: str
    name: str
    description: str


class WorkflowOutputSchemaDetail(BaseModel):
    outcome: str
    next_state: str | None = None
    artifact_id: str | None = None
    requires_approval: bool = False
    has_approval_view: bool = False
    schema_def: dict[str, Any] = {}


class WorkflowSkillDetail(BaseModel):
    id: str
    name: str


class WorkflowStateDetail(BaseModel):
    id: str
    name: str
    prompt_path: str | None = None
    skills: list[WorkflowSkillDetail] = []
    tools: list[WorkflowToolDetail] = []
    truncate_on_entry: bool = False
    include_artifacts: list[str] = []
    output_schemas: list[WorkflowOutputSchemaDetail] = []


class WorkflowDetailResponse(BaseModel):
    id: str
    name: str
    description: str
    prompt_path: str | None = None
    initial_state: str
    states: list[WorkflowStateDetail] = []


class PromptContentResponse(BaseModel):
    path: str
    content: str
