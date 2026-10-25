from __future__ import annotations

from hypergolic.contrib import contrib_path
from hypergolic.contrib.workflows.feature_development.states import (
    implementation_state,
    planning_state,
    requirements_state,
    review_state,
    summarize_state,
)
from hypergolic.harness.primitives.bundles import Workflow


feature_development_workflow = Workflow(
    id="feature-development",
    name="Product Development",
    description="End-to-end feature development: requirements → planning → implementation → review → summarize. Each phase produces an artifact that carries forward; context is truncated between phases",
    prompt_path=contrib_path("prompts/workflows/feature-development.md"),
    initial_state="requirements",
    states=[
        requirements_state,
        planning_state,
        implementation_state,
        review_state,
        summarize_state,
    ],
)
