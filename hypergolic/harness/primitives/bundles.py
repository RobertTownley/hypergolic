from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, model_validator

from hypergolic.harness.primitives.tool import Tool, ToolRegistryMixin
from hypergolic.tools.approval_view import ApprovalView


class OutputSchema(BaseModel):
    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    outcome: str
    artifact_id: str | None = None
    requires_approval: bool = False
    approval_view: ApprovalView | None = None
    schema_def: dict = Field(alias="schema")
    next_state: str | None = None


def validate_prompt_exclusivity(self: Any) -> Any:
    set_count = sum(1 for x in [self.prompt, self.prompt_path, self.prompt_fn] if x is not None)
    if set_count > 1:
        raise ValueError("Specify at most one of 'prompt', 'prompt_path', or 'prompt_fn'")
    return self


class Skill(ToolRegistryMixin, BaseModel):
    id: str
    name: str
    description: str
    #: Task vocabulary for `apropos`, carried onto the skill's advisory command.
    tags: list[str] = Field(default_factory=list)
    prompt_path: str | None = None
    prompt: str | None = None
    prompt_fn: Callable[..., str] | None = None
    tools: list[Tool] = Field(default_factory=list)
    skills: list["Skill"] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    _validate_prompt = model_validator(mode="after")(validate_prompt_exclusivity)


class WorkflowState(ToolRegistryMixin, BaseModel):
    id: str
    name: str
    prompt_path: str | None = None
    prompt: str | None = None
    prompt_fn: Callable[..., str] | None = None
    truncate_on_entry: bool = False
    include_artifacts: list[str] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    output_schemas: list[OutputSchema] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    _validate_prompt = model_validator(mode="after")(validate_prompt_exclusivity)


class Workflow(ToolRegistryMixin, BaseModel):
    id: str
    name: str
    description: str
    prompt_path: str | None = None
    prompt: str | None = None
    prompt_fn: Callable[..., str] | None = None
    initial_state: str
    states: list[WorkflowState] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    _validate_prompt = model_validator(mode="after")(validate_prompt_exclusivity)


class Role(ToolRegistryMixin, BaseModel):
    id: str
    name: str
    prompt_path: str | None = None
    prompt: str | None = None
    prompt_fn: Callable[..., str] | None = None
    skills: list[Skill] = Field(default_factory=list)
    tools: list[Any] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
    dispatch_targets: list[str] = Field(default_factory=list)
    # Per-role override of App(strip_history_thinking=...). ``None`` inherits
    # the app setting; ``False`` replays this role's thinking blocks back to
    # the model, which stops it re-deriving the same reasoning every turn at the
    # cost of billing that thinking as input on proxied stacks.
    strip_history_thinking: bool | None = None

    model_config = {"arbitrary_types_allowed": True}

    _validate_prompt = model_validator(mode="after")(validate_prompt_exclusivity)


def resolve_prompt(obj: Any, app: Any) -> str | None:
    """Resolve prompt content from prompt_fn, prompt, or prompt_path (in that order)."""
    if hasattr(obj, "prompt_fn") and obj.prompt_fn is not None:
        return obj.prompt_fn(app)
    if hasattr(obj, "prompt") and obj.prompt is not None:
        return obj.prompt
    if hasattr(obj, "prompt_path") and obj.prompt_path is not None:
        path = Path(obj.prompt_path).expanduser()
        if path.exists():
            return path.read_text()
    return None


Skill.model_rebuild()
