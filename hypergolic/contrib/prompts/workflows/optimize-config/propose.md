You are synthesizing all audit findings into a single prioritized proposal for the user to approve

This is the main approval gate: no changes are made until the user approves this proposal

## How to synthesize

Review all audit artifacts:
- `discovery` — user goals and current state
- `prompt_audit` — prompt layer findings
- `tool_audit` — tool findings
- `skills_roles_audit` — skills and roles findings
- `workflow_audit` — workflow findings
- `cross_project_review` — cross-project findings

Any artifact except `discovery` may be absent if the agent used the `suppressed` transition to skip that phase (nothing to report). Handle this gracefully

## How to present

Group changes by category:
1. **Prompts** — content to add, move, remove, or rewrite
2. **Tools** — tools to create, modify, or remove
3. **Skills** — skills to create, modify, or remove
4. **Roles** — roles to create, modify, or remove
5. **Workflows** — workflows to create or modify

For each change:
- **What**: Specific change to make
- **Why**: How it addresses a user goal or fixes a gap
- **Priority**: high / medium / low
- **Risk**: What could go wrong (usually low for config changes)

Order by priority within each category. Be honest about high-impact vs. nice-to-have

## What to produce

- **plan**: Full markdown proposal the user can review
- **changes**: Structured array of all proposed changes
- **estimated_changes_count**: Total number of discrete changes

Keep the plan readable — the user should be able to scan it quickly and understand what's proposed
