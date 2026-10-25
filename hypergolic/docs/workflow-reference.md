# Workflow Config Reference

Complete reference for all workflow configuration fields.

## Workflow

Top-level workflow definition. Register via `app.register_workflow()` or `project.register_workflow()`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | str | ✅ | — | Unique identifier (kebab-case). Used for activation and override resolution. |
| `name` | str | ✅ | — | Human-readable name displayed in the UI. |
| `description` | str | ✅ | — | Description shown to the agent and in the workflow selector. |
| `prompt_path` | str | ❌ | `None` | Path to a markdown file with workflow-level prompt context. Injected in every state. |
| `prompt` | str | ❌ | `None` | Inline prompt string. Mutually exclusive with `prompt_path` and `prompt_fn`. |
| `prompt_fn` | callable | ❌ | `None` | Dynamic prompt function. Mutually exclusive with `prompt_path` and `prompt`. |
| `initial_state` | str | ✅ | — | ID of the first state when the workflow is activated. Must match a state `id`. |
| `states` | list | ❌ | `[]` | List of `WorkflowState` objects. |
| `tools` | list | ❌ | `[]` | Tools available in all states of this workflow. |
| `skills` | list | ❌ | `[]` | Skills reachable in all states of this workflow. |

```python
from hypergolic import Workflow

Workflow(
    id="feature-development",
    name="Feature Development",
    description="End-to-end feature development",
    prompt_path="~/.hypergolic/prompts/workflows/feature-development.md",
    initial_state="requirements",
    states=[...],
)
```

## WorkflowState

Defines a single state within a workflow.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | str | ✅ | — | Unique identifier within the workflow. Referenced by `initial_state` and `next_state`. |
| `name` | str | ✅ | — | Human-readable name shown in the UI and transition markers. |
| `prompt_path` | str | ❌ | `None` | Path to a markdown file with state-specific prompt. |
| `prompt` | str | ❌ | `None` | Inline prompt string. Mutually exclusive with `prompt_path` and `prompt_fn`. |
| `prompt_fn` | callable | ❌ | `None` | Dynamic prompt function. Mutually exclusive with `prompt_path` and `prompt`. |
| `skills` | list[Skill] | ❌ | `[]` | Skills reachable while this state is current. Additive to the session's; they leave `/tools` on transition unless another scope provides them. |
| `tools` | list[Tool] | ❌ | `[]` | Tools available only in this state. |
| `truncate_on_entry` | bool | ❌ | `False` | If `True`, truncates conversation on entering this state and injects only specified artifacts. |
| `include_artifacts` | list[str] | ❌ | `[]` | Artifact IDs from prior states to inject as prompt context. Only used when `truncate_on_entry` is `True`. |
| `output_schemas` | list[OutputSchema] | ❌ | `[]` | Defines the possible exits from this state. Each generates a transition tool. |

```python
from hypergolic import WorkflowState

WorkflowState(
    id="planning",
    name="Implementation Planning",
    prompt_path="~/.hypergolic/prompts/workflows/feature-development/planning.md",
    skills=[],
    tools=[],
    truncate_on_entry=True,
    include_artifacts=["prd"],
    output_schemas=[...],
)
```

## OutputSchema

Defines one possible exit from a state. Each generates a `workflow_transition_{outcome}` tool.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `outcome` | `"success"` \| `"failure"` \| `"suppressed"` | ✅ | — | The outcome type. Determines the generated tool name. |
| `artifact_id` | str | ❌ | `None` | Logical name for the persisted artifact. Referenced by `include_artifacts` in later states. |
| `requires_approval` | bool | ❌ | `False` | If `True`, user must approve before the transition completes. Triggers the artifact review UI. |
| `approval_view` | `ApprovalView` | ❌ | `None` | Declarative spec for how the structured output is rendered in the approval UI. Block vocabulary is defined in `hypergolic/harness/primitives.py` (`ApprovalView`). |
| `schema` | dict | ✅ | — | JSON Schema defining the structured output. Must be `"type": "object"`. |
| `next_state` | str \| None | ❌ | `None` | ID of the state to transition to. `None` means exit the workflow (terminal). |

```python
from hypergolic import (
    OutputSchema, ApprovalView, MarkdownBlock, ForEachBlock,
)

OutputSchema(
    outcome="success",
    artifact_id="prd",
    requires_approval=True,
    approval_view=ApprovalView(blocks=[
        MarkdownBlock(field="document", label="PRD"),
        ForEachBlock(
            field="key_files", item_heading=".", template=[],
            label="Key files", separator="none",
        ),
        ForEachBlock(
            field="open_questions", item_heading=".", template=[],
            label="Open questions", separator="none",
        ),
    ]),
    schema={
        "type": "object",
        "properties": {
            "document": {"type": "string", "description": "The PRD"},
            "key_files": {"type": "array", "items": {"type": "string"}},
            "open_questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["document", "key_files"],
    },
    next_state="planning",
)
```

Fields referenced by the `approval_view` are rendered in the approval UI. Fields not referenced are omitted from the rendered view but remain accessible via the raw-JSON toggle in the top-right of the approval prompt. Unlisted fields are for the LLM's benefit, not human review.

## Outcome Semantics

| Outcome | Meaning | Typical Use |
|---------|---------|-------------|
| `success` | Work completed, move forward | Main path through the workflow |
| `failure` | Attempted but couldn't complete | Loop back for retry (e.g., review → implementation) |
| `suppressed` | Determined it shouldn't proceed | Graceful exit or loop back with concerns |

## Tool Generation

For each `output_schema`, a tool is generated:

- **Tool name:** `workflow_transition_{outcome}`
- **Input schema:** From the `schema` field
- **Approval:** From `requires_approval`
- **Approval UI:** From `approval_view` (optional — falls back to raw JSON)

If a state has `success` and `failure` outcomes, the agent sees:
- `workflow_transition_success`
- `workflow_transition_failure`

## Artifact Lifecycle

1. Agent calls a transition tool with structured output
2. If `artifact_id` is set, the output is persisted to the database
3. Later states reference the artifact via `include_artifacts`
4. On entry to a state with `truncate_on_entry`, artifacts are injected as prompt context
5. Artifacts persist beyond workflow completion

## Prompt Injection Order

Workflow prompts are injected after other prompt sources:

```
Role → User → Project → Session context → Active skills → Workflow prompt → State prompt → Artifact content
```

Workflow context comes last for maximum influence over agent behavior.

## Registration

Workflows can be registered globally or per-project:

```python
# Global — available in all projects
app.register_workflow(workflow)

# Per-project — available only in that project's sessions
project.register_workflow(workflow)
```

## Complete Example

```python
from hypergolic import Workflow, WorkflowState, OutputSchema

my_workflow = Workflow(
    id="my-workflow",
    name="My Workflow",
    description="Description for the agent",
    prompt_path="~/.hypergolic/prompts/workflows/my-workflow.md",
    initial_state="start",
    states=[
        WorkflowState(
            id="start",
            name="Starting Phase",
            prompt_path="~/.hypergolic/prompts/workflows/my-workflow/start.md",
            truncate_on_entry=False,
            output_schemas=[
                OutputSchema(
                    outcome="success",
                    artifact_id="start_output",
                    requires_approval=True,
                    approval_view=ApprovalView(blocks=[
                        MarkdownBlock(field="document"),
                    ]),
                    schema={
                        "type": "object",
                        "properties": {
                            "document": {"type": "string"},
                        },
                        "required": ["document"],
                    },
                    next_state="finish",
                ),
            ],
        ),
        WorkflowState(
            id="finish",
            name="Finish",
            truncate_on_entry=True,
            include_artifacts=["start_output"],
            output_schemas=[
                OutputSchema(
                    outcome="success",
                    schema={
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                        },
                        "required": ["summary"],
                    },
                    next_state=None,
                ),
            ],
        ),
    ],
)

# Register it
app.register_workflow(my_workflow)
```
