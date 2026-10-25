You are auditing all configured tools for quality, placement, and completeness

## Tools to evaluate

Read `~/.hypergolic/main.py` and find all tool registrations:
- User-level via `app.register_tool()`
- Per-project via `project.register_tool()`
- Skill-gated (tools defined within skill configs)
- Built-in via `app.use_defaults()` (defined in the installed `hypergolic` package, customizable via `override_tool` / `remove_tool` / `modify_role` in `main.py`)

For each tool, read the script it references to understand what it actually does

## What to check

**Description quality:** The description is the agent's only guide for when to use a tool: what it does AND when to reach for it. Bad: "Run tests." Good: "Run the project's pytest suite. Use after making code changes to verify nothing is broken. Returns exit code 0 on success."

**Parameter quality:** Well-named and well-described? Sensible defaults? Required parameters truly required?

**Placement:** Should the tool live at a different level?
- Tools using personal credentials/paths → user-level (`app.register_tool()`) or per-project (`project.register_tool()`)
- Tools any contributor benefits from → user-level (document in project README for team sharing)
- Tools only relevant during specific tasks → skill-gated

**Timeout:** Matches expected execution time? A 60s test suite shouldn't have a 30s timeout

**Approval settings:** Read-only tools should not require approval; mutating tools (deploy, delete, write) should

**Missing tools:** From the discovery artifact, what tools would make the agent more effective? Consider:
- Test running (full suite, subsets, specific files)
- Linting and type checking
- Building
- API interaction (if applicable)
- Database operations (if applicable)
- Deployment (if applicable)

**Obsolete tools:** References to removed scripts, defunct services, or workflows the user no longer follows?

**Script quality:** For script-backed tools: does the script handle errors? Useful output? A uv script (preferred) or plain shell command?

## What to produce

A findings report plus structured lists of tools to add, modify, and remove, each with rationale
