from hypergolic.contrib import contrib_path
from hypergolic.harness.primitives.bundles import Role
from hypergolic.contrib.tools.command import command_tool
from hypergolic.contrib.tools.review import ReviewTool
from hypergolic.contrib.tools.ui_token import mint_ui_token_tool
from hypergolic.contrib.skills.registry import (
    git_skill,
    harness_performance_skill,
    history_skill,
    manage_mcp_skill,
    product_management_skill,
    REVIEWER_SKILLS,
)
from hypergolic.contrib.workflows import ALL_CONTRIB_WORKFLOWS

generalist_role = Role(
    id="generalist",
    name="Generalist",
    prompt_path=contrib_path("prompts/roles/generalist.md"),
    tools=[
        command_tool,
        mint_ui_token_tool,
    ],
    skills=[
        git_skill,
        product_management_skill,
        manage_mcp_skill,
        history_skill,
        harness_performance_skill,
    ],
    workflows=ALL_CONTRIB_WORKFLOWS,
    dispatch_targets=["generalist", "worker", "researcher"],
)

worker_role = Role(
    id="worker",
    name="Worker",
    prompt_path=contrib_path("prompts/roles/worker.md"),
    tools=[
        ReviewTool,
    ],
)

reviewer_role = Role(
    id="reviewer",
    name="Reviewer",
    prompt_path=contrib_path("prompts/roles/reviewer.md"),
    skills=REVIEWER_SKILLS,
    # A reviewer re-reads the same diff every turn; without its own thinking in
    # history it re-derives the same analysis from scratch each time.
    strip_history_thinking=False,
)

researcher_role = Role(
    id="researcher",
    name="Researcher",
    prompt_path=contrib_path("prompts/roles/researcher.md"),
)

ALL_CONTRIB_ROLES = [
    generalist_role,
    worker_role,
    researcher_role,
    reviewer_role,
]
