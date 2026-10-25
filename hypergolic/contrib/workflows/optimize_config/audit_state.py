"""Helper for the four near-identical audit states in optimize-config.

Each audit state reads the discovery artifact, produces findings, and
can skip ahead via the ``suppressed`` outcome when nothing actionable
surfaces. Centralizing the shape keeps individual audit definitions to
one line each.
"""
from __future__ import annotations

from hypergolic.contrib import contrib_path
from hypergolic.contrib.workflows.optimize_config.schemas import (
    AUDIT_FINDINGS_SCHEMA,
    AUDIT_SKIPPED_SCHEMA,
)
from hypergolic.harness.primitives.bundles import OutputSchema, WorkflowState
from hypergolic.tools.approval_view import (
    ApprovalView,
    ForEachBlock,
    MarkdownBlock,
)


def build_audit_state(
    state_id: str,
    name: str,
    prompt_filename: str,
    artifact_id: str,
    next_state: str,
) -> WorkflowState:
    return WorkflowState(
        id=state_id,
        name=name,
        prompt_path=contrib_path(f"prompts/workflows/optimize-config/{prompt_filename}"),
        truncate_on_entry=True,
        include_artifacts=["discovery"],
        output_schemas=[
            OutputSchema(
                outcome="success",
                artifact_id=artifact_id,
                requires_approval=True,
                approval_view=ApprovalView(blocks=[
                    MarkdownBlock(field="findings", label="Findings"),
                    ForEachBlock(
                        field="recommendations",
                        template=[],
                        item_heading=".",
                        label="Recommendations",
                        separator="divider",
                        empty_text="None — nothing actionable to recommend.",
                    ),
                ]),
                schema=AUDIT_FINDINGS_SCHEMA,
                next_state=next_state,
            ),
            OutputSchema(
                outcome="suppressed",
                artifact_id=artifact_id,
                schema=AUDIT_SKIPPED_SCHEMA,
                next_state=next_state,
            ),
        ],
    )
