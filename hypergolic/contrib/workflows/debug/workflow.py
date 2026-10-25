from __future__ import annotations

from hypergolic.contrib import contrib_path
from hypergolic.contrib.workflows.debug.states import (
    investigation_state,
    resolving_state,
    validating_state,
)
from hypergolic.harness.primitives.bundles import Workflow


debug_workflow = Workflow(
    id="debug",
    name="Debugging",
    description="Investigate → resolve → validate a reported bug. Each phase produces an artifact; context is truncated between phases",
    prompt_path=contrib_path("prompts/workflows/debug.md"),
    initial_state="investigation",
    states=[
        investigation_state,
        resolving_state,
        validating_state,
    ],
)
