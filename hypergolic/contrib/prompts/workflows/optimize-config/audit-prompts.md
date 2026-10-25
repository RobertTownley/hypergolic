You are auditing all prompt layers for quality, placement, and completeness

## Prompt layers to evaluate

Read each prompt file in assembly order:
1. **Role prompt** — the active role's prompt (built-in defaults ship in the installed `hypergolic` package; user overrides in `~/.hypergolic/prompts/`)
2. **User custom prompts** — `~/.hypergolic/prompts/`
3. **Project prompt** — the path in `Project.prompt_path` in `~/.hypergolic/main.py`
4. **Skill prompts** — any active skills' prompts

Read `~/.hypergolic/main.py` to find prompt paths for each project and skill

## What to check

**Redundancy:** Same information repeated across layers? Content should live at exactly one level

**Misplacement:** Project-specific information in the user system prompt? Personal preferences in the project prompt (which gets committed)? Common mistakes:
- Personal code style preferences, or generic instructions that apply to all projects, in the project prompt (should be user custom prompts in `~/.hypergolic/prompts/`)
- Project architecture in a user custom prompt when the team should see it (should be project prompt)

**Gaps:** What's missing entirely?
- Does the project prompt explain architecture, tech stack, key conventions?
- How to run tests, build, lint?
- Domain concepts the agent needs to understand?
- Undocumented team conventions (PR format, commit style, naming)?

**Verbosity:** Every prompt token is consumed in every message. Remove instructions that don't pull their weight — things the agent would do anyway, or so rare they should be a skill instead

**Quality:** Are instructions clear and actionable? Do they explain *why*, not just *what*? Contradictions between layers?

## What to produce

A findings report with specific, actionable recommendations. For each issue:
- **location**: Which prompt file
- **issue**: What's wrong
- **recommendation**: What to change
- **priority**: high (actively hurting), medium (room for improvement), low (nice to have)
