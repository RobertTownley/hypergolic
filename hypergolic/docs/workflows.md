# Workflows

Workflows introduce a configurable state machine that governs how a session progresses through defined phases of work. Each state has its own prompt, tools, skills, and structured output contracts. Transitions create natural truncation points, carrying forward only the artifacts that matter.

## When to Use Workflows

Use workflows when a task has:

- **Clear phases** that benefit from different prompts, tools, or agent personas
- **Structured handoffs** where output from one phase feeds the next
- **Context management needs** where the conversation can be truncated between phases, preserving only key artifacts
- **Quality gates** where user approval is required before proceeding

For freeform conversations, ad-hoc questions, or quick tasks, workflows are unnecessary — regular sessions work fine.

## Anatomy of a Workflow

A workflow is defined in Python with the `Workflow` and `WorkflowState` classes:

```python
from hypergolic import Workflow, WorkflowState, OutputSchema

workflow = Workflow(
    id="feature-development",
    name="Feature Development",
    description="End-to-end feature development from requirements through review",
    prompt_path="~/.hypergolic/prompts/workflows/feature-development.md",
    initial_state="requirements",
    states=[...],
)
```

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (kebab-case) |
| `name` | Human-readable name shown in the UI |
| `description` | Helps the agent decide when to suggest this workflow |
| `prompt_path` | Markdown file with workflow-level context (injected in all states) |
| `initial_state` | ID of the first state when the workflow activates |
| `states` | List of `WorkflowState` objects |

## Workflow States

Each state defines what the agent should do in that phase:

```python
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

| Field | Description |
|-------|-------------|
| `prompt_path` | State-specific prompt injected when this state is active |
| `skills` | Skills reachable while this state is current (additive to the session's) |
| `tools` | Tools available only in this state |
| `truncate_on_entry` | If `True`, truncates conversation and injects only specified artifacts |
| `include_artifacts` | Artifact IDs from prior states to inject as context |
| `output_schemas` | Defines how the agent exits this state |

### Truncation on Entry

When `truncate_on_entry` is `True`, entering the state:

1. Marks all existing messages as truncated
2. Injects artifacts from `include_artifacts` as context
3. Injects a system message orienting the agent to its new state

This is the key benefit of workflows — each phase starts with a clean context window containing only the relevant artifacts from prior phases.

## Output Schemas and Transitions

Each state defines one or more outcomes via `output_schemas`. Each outcome generates a tool the agent can call:

```python
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
            "document": {"type": "string"},
            "key_files": {"type": "array", "items": {"type": "string"}},
            "open_questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["document", "key_files"],
    },
    next_state="planning",
)
```

| Field | Description |
|-------|-------------|
| `outcome` | One of `"success"`, `"failure"`, or `"suppressed"` |
| `artifact_id` | Logical name for persisted output (referenced by `include_artifacts`) |
| `requires_approval` | If `True`, user must approve before the transition completes |
| `approval_view` | Declarative `ApprovalView` spec shaping the human-facing approval UI. Block vocabulary is defined in `hypergolic/harness/primitives.py` (`ApprovalView`). |
| `schema` | JSON Schema defining the structured output |
| `next_state` | ID of the next state, or `None` to exit the workflow |

### Outcome Semantics

- **success** — Work completed successfully, move forward
- **failure** — Attempted but unable to complete (may loop back to retry)
- **suppressed** — Determined the work shouldn't proceed (prerequisites missing, unsafe, etc.)

Each outcome generates a tool named `workflow_transition_{outcome}`. For example, a state with `success` and `failure` outcomes gives the agent `workflow_transition_success` and `workflow_transition_failure`.

## Activation

Workflows can be activated two ways:

### User-Initiated

The chat input includes a workflow selector. Pick a workflow before sending your message, and the workflow activates with your message as the initial input.

### Agent-Initiated

The agent has an `activate_workflow` tool. It can suggest and activate a workflow based on the conversation context.

## Artifacts

When an outcome has an `artifact_id`, the structured output is persisted as an artifact. Artifacts are:

- **Stored in the database** with session, workflow, state, and outcome metadata
- **Injected into subsequent states** via `include_artifacts`
- **Versioned** — if a state is visited multiple times (e.g., implementation → review → implementation), each produces a separate artifact with a timestamp

## Approval and Annotation

When `requires_approval` is `True`, the transition triggers the artifact review UI:

- Fields referenced by the `approval_view` blocks are rendered in the UI
- Fields not referenced are omitted from the rendered view but available via the "Rendered ↔ Raw JSON" toggle in the top-right (**J**)
- Users can highlight text in markdown blocks and attach inline annotations
- Keyboard shortcuts: **Y** to approve, **N** to reject, **D** to reject with reason, **J** to toggle raw JSON

Annotations are sent to the agent as part of the tool result, providing targeted feedback on specific parts of the artifact.

### Approval View Blocks

`ApprovalView` composes from a small set of block primitives:

| Block | Use case |
|-------|----------|
| `MarkdownBlock` | Rendered markdown — PRD documents, plans, analysis |
| `CodeBlock` | Syntax-highlighted code with optional max-height scroll |
| `TextBlock` | Short plain-text value |
| `BadgeBlock` | Inline chip/tag for status, verdict, tier |
| `ForEachBlock` | Repeat a nested template per item in a list field |

Complete block reference: `ApprovalView` in `hypergolic/harness/primitives.py`.

## Example: Feature Development

The feature-development workflow has five states:

```
requirements → planning → implementation → review → summarize
```

1. **Requirements** — Gathers requirements, produces a PRD (user approves)
2. **Planning** — Reviews the PRD, produces an implementation plan (user approves)
3. **Implementation** — Follows the plan, writes code and tests
4. **Review** — Reviews against the PRD, runs tests (user approves pass/fail)
5. **Summarize** — Produces a feature summary (terminal state)

Backward transitions: implementation can loop back to planning (suppressed), review can loop back to implementation (failure).

## Example: Debug

The debug workflow has four states:

```
understanding → reproducing → resolving → validating
```

1. **Understanding** — Analyzes the bug, forms a reproduction strategy (user approves)
2. **Reproducing** — Executes the strategy, confirms the bug exists
3. **Resolving** — Implements the fix with regression tests
4. **Validating** — Confirms the fix works and no regressions (terminal state)

Backward transitions: reproducing can loop back to understanding (failure), resolving can loop back to understanding (suppressed), validating can loop back to resolving (failure).

## Designing Your Own Workflows

### Tips

- **Make state prompts self-contained.** Assume the agent only has the artifacts and prompt, not prior conversation.
- **Use `truncate_on_entry` aggressively.** The whole point of workflows is structured context management.
- **Use `include_artifacts` to carry forward only what's needed.** Don't include everything — be selective.
- **Use `requires_approval` for quality gates** where user judgment is critical.
- **Use `approval_view`** to shape the human-facing approval UI with `MarkdownBlock`, `CodeBlock`, `BadgeBlock`, `ForEachBlock`, etc.
- **Design backward transitions** for recovery — failure loops back for another attempt, suppressed exits gracefully.

### Prompt Design

- **Workflow-level prompts** set the overall context ("you are developing a feature end-to-end")
- **State-level prompts** set specific behavior ("gather requirements by asking these questions")
- State prompts should explain what the phase accomplishes, the expected output structure, the available transition tools, and how to use artifacts from prior phases

### Registration

Register workflows globally or per-project:

```python
# Available in all projects
app.register_workflow(workflow)

# Available only in this project
project.register_workflow(workflow)
```

See the [Workflow Config Reference](workflow-reference.md) for complete field documentation.
