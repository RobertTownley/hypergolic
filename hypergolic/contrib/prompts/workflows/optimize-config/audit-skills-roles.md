You are auditing skills and roles for quality, placement, and completeness

## Skills to evaluate

Read `~/.hypergolic/main.py` and find all skill registrations via `app.register_skill()`. For each custom skill, read its prompt file to assess quality

## What to check for skills

**Prompt quality:**
- Explains *why*, not just *what* — LLMs respond better to reasoning than rigid commands
- Lean — no instructions that don't pull their weight
- Examples where they'd help
- Imperative form ("Examine the schema" not "You should examine the schema")

**Description quality:** The description determines whether the agent surfaces the skill to users. Test it:
- Would 3 realistic prompts that should trigger this skill match it?
- Would 2 adjacent-but-different prompts correctly NOT match?

**Placement:** Personal domain expertise → user-level (`app.register_skill()`). Team/project domain expertise → user-level (document in project README for team sharing)

**Missing skills:** From the discovery artifact, would common tasks benefit from skill abstraction? Look for:
- Complex domain knowledge needed intermittently
- Tasks requiring a specific persona or approach
- Knowledge too heavy for a prompt but too important to omit

**Obsolete skills:** References to outdated technologies, defunct processes, or domains the user no longer works in

## Roles to evaluate

Find all role registrations via `app.register_role()` in `main.py` and read each role's prompt file

## What to check for roles

**Prompt quality:** Well-written and focused?

**Skill/tool assignments:** Does each role reach the right skills and tools?

**Missing roles:** Does the user operate in fundamentally different modes that would benefit from role switching? Common patterns:
- Code review vs. implementation
- Architecture/design vs. coding
- Documentation

## What to produce

A findings report plus structured recommendations for skills and roles (create, modify, remove)
