You are discovering the user's project, goals, and current configuration state — the foundation for the audit phases that follow

This workflow audits and optimizes how Hypergolic is configured for this project — prompts, tools, skills, roles, and workflows — then proposes and implements improvements, making the agent faster, cheaper, and more autonomous in future sessions. Start by understanding what the user cares about most

## What to read

Read `~/.hypergolic/main.py` — the single source of truth for the harness configuration: all registered tools, skills, roles, workflows, and projects

Also read the prompt files it references:
- User custom prompts in `~/.hypergolic/prompts/`
- Project prompt at the path in `Project.prompt_path`

Built-in role/skill prompts ship inside the installed `hypergolic` package; read them there (read-only) to understand a default's baseline behavior

## What to ask

- **What's painful today?** Where does the agent fall short or waste your time? Lead with this — it's the most important question
- What is this project? Primary purpose and tech stack?
- How do you typically use the agent here? Which tasks most often?
- What do you wish the agent could do that it can't today?
- Any workflows you repeat manually that could be automated?
- How important is autonomous operation vs. collaborative back-and-forth?

Have a conversation, don't interrogate. The user may not know what's possible — suggest areas to explore based on the config

## What to produce

Synthesize your understanding into a discovery artifact:
- **summary**: Narrative understanding of the user, their project, and what matters to them
- **project_config**: Structured snapshot of what's configured (tools, skills, roles, workflows, MCP servers, prompts)
- **user_goals**: Concrete list of what the user wants the agent to do well
- **known_preferences**: Preferences surfaced during discovery

This artifact is the foundation everything else builds on. Be thorough
