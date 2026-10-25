"""WorkflowState definitions for the feature-development workflow."""
from __future__ import annotations

from hypergolic.contrib import contrib_path
from hypergolic.contrib.skills.registry import product_management_skill
from hypergolic.contrib.workflows.feature_development.schemas import (
    IMPLEMENTATION_BLOCKED_SCHEMA,
    IMPLEMENTATION_SCHEMA,
    PLAN_SCHEMA,
    PRD_SCHEMA,
    REVIEW_FAIL_SCHEMA,
    REVIEW_PASS_SCHEMA,
    SUMMARY_SCHEMA,
)
from hypergolic.harness.primitives.bundles import OutputSchema, WorkflowState
from hypergolic.tools.approval_view import (
    ApprovalView,
    BadgeBlock,
    ForEachBlock,
    MarkdownBlock,
)


requirements_state = WorkflowState(
    id="requirements",
    name="Requirements",
    prompt_path=contrib_path("prompts/workflows/feature-development/requirements.md"),
    skills=[product_management_skill],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="prd",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                MarkdownBlock(field="document", label="PRD"),
                ForEachBlock(
                    field="key_files",
                    template=[],
                    item_heading=".",
                    label="Key files",
                    separator="none",
                ),
                ForEachBlock(
                    field="open_questions",
                    template=[],
                    item_heading=".",
                    label="Open questions",
                    separator="none",
                    empty_text="None — requirements are resolved.",
                ),
            ]),
            schema=PRD_SCHEMA,
            next_state="planning",
        ),
    ],
)

planning_state = WorkflowState(
    id="planning",
    name="Planning",
    prompt_path=contrib_path("prompts/workflows/feature-development/planning.md"),
    truncate_on_entry=True,
    include_artifacts=["prd"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="plan",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                MarkdownBlock(field="document", label="Implementation plan"),
                ForEachBlock(
                    field="risks",
                    template=[],
                    item_heading=".",
                    label="Risks",
                    separator="none",
                    empty_text="None flagged.",
                ),
            ]),
            schema=PLAN_SCHEMA,
            next_state="implementation",
        ),
    ],
)

implementation_state = WorkflowState(
    id="implementation",
    name="Implementation",
    prompt_path=contrib_path("prompts/workflows/feature-development/implementation.md"),
    truncate_on_entry=True,
    include_artifacts=["prd", "plan"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="implementation",
            schema=IMPLEMENTATION_SCHEMA,
            next_state="review",
        ),
        OutputSchema(
            outcome="suppressed",
            artifact_id="implementation",
            schema=IMPLEMENTATION_BLOCKED_SCHEMA,
            next_state="planning",
        ),
    ],
)

review_state = WorkflowState(
    id="review",
    name="Review",
    prompt_path=contrib_path("prompts/workflows/feature-development/review.md"),
    truncate_on_entry=True,
    include_artifacts=["prd", "plan", "implementation"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="review",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                BadgeBlock(field="verdict", label="Verdict", tone="info"),
                MarkdownBlock(field="notes", label="Review notes"),
            ]),
            schema=REVIEW_PASS_SCHEMA,
            next_state="summarize",
        ),
        OutputSchema(
            outcome="failure",
            artifact_id="review",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                BadgeBlock(field="verdict", label="Verdict", tone="danger"),
                ForEachBlock(
                    field="blocking_issues",
                    template=[],
                    item_heading=".",
                    label="Blocking issues",
                    separator="divider",
                ),
            ]),
            schema=REVIEW_FAIL_SCHEMA,
            next_state="implementation",
        ),
    ],
)

summarize_state = WorkflowState(
    id="summarize",
    name="Summarize",
    prompt_path=contrib_path("prompts/workflows/feature-development/summarize.md"),
    truncate_on_entry=True,
    include_artifacts=["prd", "plan", "implementation", "review"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="summary",
            schema=SUMMARY_SCHEMA,
            next_state=None,
        ),
    ],
)
