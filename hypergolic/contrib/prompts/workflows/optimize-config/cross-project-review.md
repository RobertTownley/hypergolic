You are reviewing the user's configuration across projects to identify patterns and shared opportunities

## What to read

Read `~/.hypergolic/main.py` — all project definitions. For each project:
- Read its prompt file at `Project.prompt_path`
- Note which tools are registered via `project.register_tool()` vs shared via `app.register_tool()`

## Cross-project patterns

Look for patterns to promote to user-level:
- **Shared tools:** Similar tools registered in multiple projects via `project.register_tool()`? A test runner, linter, or build tool appearing in 2+ projects should probably move to `app.register_tool()`
- **Shared skills:** Domain expertise spanning projects (e.g., "Python best practices" active in 3 Python projects) should register at user level via `app.register_skill()`
- **Shared prompt content:** Instructions repeated in multiple project prompts should move to a user custom prompt in `~/.hypergolic/prompts/`
- **Shared preferences:** Code style, communication, or workflow preferences that look project-specific but are actually personal

## Scope

Improvements requiring codebase changes rather than config changes are out-of-scope follow-ups, not config recommendations

## What to produce

A findings report plus:
- **user_level_recommendations**: Things to consolidate at user-level across projects
