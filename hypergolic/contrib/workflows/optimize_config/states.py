"""WorkflowState definitions for the optimize-config workflow."""
from __future__ import annotations

from hypergolic.contrib import contrib_path
from hypergolic.contrib.workflows.optimize_config.audit_state import build_audit_state
from hypergolic.contrib.workflows.optimize_config.schemas import (
    AUDIT_SKIPPED_SCHEMA,
    CROSS_PROJECT_SCHEMA,
    DISCOVERY_SCHEMA,
    IMPLEMENTATION_SCHEMA,
    PROPOSAL_SCHEMA,
    SUMMARY_SCHEMA,
)
from hypergolic.harness.primitives.bundles import OutputSchema, WorkflowState
from hypergolic.tools.approval_view import (
    ApprovalView,
    ForEachBlock,
    MarkdownBlock,
)


discovery_state = WorkflowState(
    id="discovery",
    name="Discovery",
    prompt_path=contrib_path("prompts/workflows/optimize-config/discovery.md"),
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="discovery",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                MarkdownBlock(field="summary", label="Summary"),
                MarkdownBlock(field="project_config", label="Current configuration"),
                ForEachBlock(
                    field="user_goals",
                    template=[],
                    item_heading=".",
                    label="User goals",
                    separator="none",
                ),
                ForEachBlock(
                    field="known_preferences",
                    template=[],
                    item_heading=".",
                    label="Known preferences",
                    separator="none",
                    empty_text="None captured yet.",
                ),
            ]),
            schema=DISCOVERY_SCHEMA,
            next_state="audit-prompts",
        ),
    ],
)

audit_prompts_state = build_audit_state(
    "audit-prompts", "Audit Prompts", "audit-prompts.md", "prompt_audit", "audit-tools",
)
audit_tools_state = build_audit_state(
    "audit-tools", "Audit Tools", "audit-tools.md", "tool_audit", "audit-skills-roles",
)
audit_skills_roles_state = build_audit_state(
    "audit-skills-roles", "Audit Skills & Roles", "audit-skills-roles.md",
    "skills_roles_audit", "audit-workflows",
)
audit_workflows_state = build_audit_state(
    "audit-workflows", "Audit Workflows", "audit-workflows.md",
    "workflow_audit", "cross-project-review",
)

cross_project_review_state = WorkflowState(
    id="cross-project-review",
    name="Cross-Project Review",
    prompt_path=contrib_path("prompts/workflows/optimize-config/cross-project-review.md"),
    truncate_on_entry=True,
    include_artifacts=["discovery"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="cross_project_review",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                MarkdownBlock(field="findings", label="Findings"),
                ForEachBlock(
                    field="user_level_recommendations",
                    template=[],
                    item_heading=".",
                    label="User-level consolidations",
                    separator="divider",
                    empty_text="None — no cross-project patterns to consolidate.",
                ),
            ]),
            schema=CROSS_PROJECT_SCHEMA,
            next_state="propose",
        ),
        OutputSchema(
            outcome="suppressed",
            artifact_id="cross_project_review",
            schema=AUDIT_SKIPPED_SCHEMA,
            next_state="propose",
        ),
    ],
)

propose_state = WorkflowState(
    id="propose",
    name="Propose",
    prompt_path=contrib_path("prompts/workflows/optimize-config/propose.md"),
    truncate_on_entry=True,
    include_artifacts=[
        "discovery",
        "prompt_audit",
        "tool_audit",
        "skills_roles_audit",
        "workflow_audit",
        "cross_project_review",
    ],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="proposal",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                MarkdownBlock(field="plan", label="Optimization proposal"),
                ForEachBlock(
                    field="changes",
                    template=[],
                    item_heading=".",
                    label="Discrete changes",
                    separator="divider",
                ),
            ]),
            schema=PROPOSAL_SCHEMA,
            next_state="implement",
        ),
    ],
)

implement_state = WorkflowState(
    id="implement",
    name="Implement",
    prompt_path=contrib_path("prompts/workflows/optimize-config/implement.md"),
    truncate_on_entry=True,
    include_artifacts=["discovery", "proposal"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="implementation",
            schema=IMPLEMENTATION_SCHEMA,
            next_state="summarize",
        ),
    ],
)

summarize_state = WorkflowState(
    id="summarize",
    name="Summarize",
    prompt_path=contrib_path("prompts/workflows/optimize-config/summarize.md"),
    truncate_on_entry=True,
    include_artifacts=["discovery", "proposal", "implementation"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="summary",
            schema=SUMMARY_SCHEMA,
            next_state=None,
        ),
    ],
)
