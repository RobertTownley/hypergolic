from __future__ import annotations

from hypergolic.contrib import contrib_path
from hypergolic.contrib.workflows.optimize_config.states import (
    audit_prompts_state,
    audit_skills_roles_state,
    audit_tools_state,
    audit_workflows_state,
    cross_project_review_state,
    discovery_state,
    implement_state,
    propose_state,
    summarize_state,
)
from hypergolic.harness.primitives.bundles import Workflow


optimize_config_workflow = Workflow(
    id="optimize-config",
    name="Optimize Config",
    description="Audit and improve this project's Hypergolic configuration: discovery → audit prompts/tools/skills/roles/workflows → cross-project review → propose → implement → summarize. Audit phases can be skipped when nothing actionable surfaces",
    prompt_path=contrib_path("prompts/workflows/optimize-config.md"),
    initial_state="discovery",
    states=[
        discovery_state,
        audit_prompts_state,
        audit_tools_state,
        audit_skills_roles_state,
        audit_workflows_state,
        cross_project_review_state,
        propose_state,
        implement_state,
        summarize_state,
    ],
)
