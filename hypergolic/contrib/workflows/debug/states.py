"""WorkflowState definitions for the debug workflow."""
from __future__ import annotations

from hypergolic.contrib import contrib_path
from hypergolic.contrib.workflows.debug.schemas import (
    FIX_BLOCKED_SCHEMA,
    FIX_SCHEMA,
    INVESTIGATION_SCHEMA,
    VALIDATION_FAIL_SCHEMA,
    VALIDATION_PASS_SCHEMA,
)
from hypergolic.harness.primitives.bundles import OutputSchema, WorkflowState
from hypergolic.tools.approval_view import (
    ApprovalView,
    BadgeBlock,
    ForEachBlock,
    MarkdownBlock,
)


investigation_state = WorkflowState(
    id="investigation",
    name="Investigation",
    prompt_path=contrib_path("prompts/workflows/debug/investigation.md"),
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="investigation",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                MarkdownBlock(field="root_cause", label="Root cause"),
                MarkdownBlock(field="reproduction", label="Reproduction"),
                ForEachBlock(
                    field="affected_files",
                    template=[],
                    item_heading=".",
                    label="Affected files",
                    separator="none",
                ),
                MarkdownBlock(field="evidence", label="Evidence"),
            ]),
            schema=INVESTIGATION_SCHEMA,
            next_state="resolving",
        ),
    ],
)

resolving_state = WorkflowState(
    id="resolving",
    name="Resolving",
    prompt_path=contrib_path("prompts/workflows/debug/resolving.md"),
    truncate_on_entry=True,
    include_artifacts=["investigation"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="fix",
            schema=FIX_SCHEMA,
            next_state="validating",
        ),
        OutputSchema(
            outcome="suppressed",
            artifact_id="fix",
            schema=FIX_BLOCKED_SCHEMA,
            next_state="investigation",
        ),
    ],
)

validating_state = WorkflowState(
    id="validating",
    name="Validating",
    prompt_path=contrib_path("prompts/workflows/debug/validating.md"),
    truncate_on_entry=True,
    include_artifacts=["investigation", "fix"],
    output_schemas=[
        OutputSchema(
            outcome="success",
            artifact_id="validation",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                BadgeBlock(field="verdict", label="Verdict", tone="info"),
                MarkdownBlock(field="notes", label="Notes"),
            ]),
            schema=VALIDATION_PASS_SCHEMA,
            next_state=None,
        ),
        OutputSchema(
            outcome="failure",
            artifact_id="validation",
            requires_approval=True,
            approval_view=ApprovalView(blocks=[
                BadgeBlock(field="verdict", label="Verdict", tone="danger"),
                ForEachBlock(
                    field="failures",
                    template=[],
                    item_heading=".",
                    label="Failures",
                    separator="divider",
                ),
            ]),
            schema=VALIDATION_FAIL_SCHEMA,
            next_state="resolving",
        ),
    ],
)
