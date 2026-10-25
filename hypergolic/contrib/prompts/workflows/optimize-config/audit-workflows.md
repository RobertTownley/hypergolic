You are auditing workflows for quality, design, and completeness

## Workflows to evaluate

Read `~/.hypergolic/main.py` and find all workflow registrations:
- User-level via `app.register_workflow()`
- Built-in (feature-development, debug, optimize-config)

For custom workflows, read all prompt files (workflow-level and state-level)

## What to check

**State design:** Does each state have a clear purpose? Any states doing too much, or too granular?

**Truncation strategy:** Is `truncate_on_entry` used effectively? Workflows exist for structured context management — states that don't truncate accumulate unbounded conversation history

**Artifact design:** Do output schemas capture everything the next state needs? Are `include_artifacts` lists correct — not too broad (wasting context) or too narrow (missing information)?

**Prompt quality:** State prompts should:
- Be self-contained — assume the agent has only artifacts and the prompt, no prior conversation
- Explain what the phase accomplishes
- Describe expected output structure
- Reference available artifacts and how to use them

**Approval gates:** Are `requires_approval` flags at major decision points, not every step?

**Skill assignments:** Are the right skills active in each state?

**Missing workflows:** From the discovery artifact, are there repeatable multi-step processes that would benefit from workflow structure? Common patterns:
- Code review
- Release/deployment
- Onboarding (new team members or new domains)
- Data pipelines
- Incident response

## What to produce

A findings report plus structured recommendations for workflows (create, modify, remove). For new workflow suggestions, briefly describe the states and their purpose
