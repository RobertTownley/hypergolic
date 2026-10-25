"""Cross-cutting invariants for every built-in workflow.

Parametrized over ``ALL_CONTRIB_WORKFLOWS`` so adding a new workflow
automatically gets it covered: unique IDs, valid state graphs, prompt
files that exist on disk, and approval-view fields that reference
fields declared in their schemas.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hypergolic.contrib.workflows import ALL_CONTRIB_WORKFLOWS
from hypergolic.harness.primitives.bundles import Workflow
from hypergolic.tools.approval_view import ForEachBlock


def test_unique_workflow_ids():
    ids = [w.id for w in ALL_CONTRIB_WORKFLOWS]
    assert len(ids) == len(set(ids)), f"Duplicate workflow IDs: {ids}"


@pytest.mark.parametrize("workflow", ALL_CONTRIB_WORKFLOWS, ids=lambda w: w.id)
def test_initial_state_exists(workflow: Workflow):
    state_ids = {s.id for s in workflow.states}
    assert workflow.initial_state in state_ids


@pytest.mark.parametrize("workflow", ALL_CONTRIB_WORKFLOWS, ids=lambda w: w.id)
def test_state_transitions_reference_known_states(workflow: Workflow):
    state_ids = {s.id for s in workflow.states}
    for state in workflow.states:
        for out in state.output_schemas:
            if out.next_state is not None:
                assert out.next_state in state_ids, (
                    f"{workflow.id}.{state.id} outcome {out.outcome!r} "
                    f"points at unknown state {out.next_state!r}"
                )


@pytest.mark.parametrize("workflow", ALL_CONTRIB_WORKFLOWS, ids=lambda w: w.id)
def test_prompt_files_exist(workflow: Workflow):
    prompt_paths: list[str] = []
    if workflow.prompt_path:
        prompt_paths.append(workflow.prompt_path)
    for state in workflow.states:
        if state.prompt_path:
            prompt_paths.append(state.prompt_path)

    missing = [p for p in prompt_paths if not Path(p).exists()]
    assert not missing, f"Missing prompt files for {workflow.id}: {missing}"


@pytest.mark.parametrize("workflow", ALL_CONTRIB_WORKFLOWS, ids=lambda w: w.id)
def test_unique_state_ids(workflow: Workflow):
    ids = [s.id for s in workflow.states]
    assert len(ids) == len(set(ids)), f"Duplicate state IDs in {workflow.id}: {ids}"


@pytest.mark.parametrize("workflow", ALL_CONTRIB_WORKFLOWS, ids=lambda w: w.id)
def test_workflow_reaches_terminal_state(workflow: Workflow):
    """Some outcome somewhere must have next_state=None, or the workflow can't end."""
    has_terminal = any(
        out.next_state is None
        for state in workflow.states
        for out in state.output_schemas
    )
    assert has_terminal, f"Workflow {workflow.id} has no terminal outcome"


@pytest.mark.parametrize("workflow", ALL_CONTRIB_WORKFLOWS, ids=lambda w: w.id)
def test_approval_view_fields_exist_in_schema(workflow: Workflow):
    """Every ``field`` referenced by an approval-view block should be declared
    in the schema it describes. Prevents silent renders of undefined fields.
    """
    for state in workflow.states:
        for out in state.output_schemas:
            if out.approval_view is None:
                continue
            schema_fields = set(out.schema_def.get("properties", {}).keys())
            for block in out.approval_view.blocks:
                field = getattr(block, "field", None)
                if not field or field == ".":
                    continue
                # ForEachBlock.field is the list to iterate at the schema
                # root; its template fields resolve against items, not the
                # schema root, so they're not validated here.
                if isinstance(block, ForEachBlock):
                    assert field in schema_fields, (
                        f"{workflow.id}.{state.id}.{out.outcome}: ForEach over "
                        f"unknown field {field!r} (schema has {schema_fields})"
                    )
                    continue
                assert field in schema_fields, (
                    f"{workflow.id}.{state.id}.{out.outcome}: block references "
                    f"unknown field {field!r} (schema has {schema_fields})"
                )
