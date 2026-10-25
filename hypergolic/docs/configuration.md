# Configuration

Hypergolic is configured through a Python-based harness that lives at `~/.hypergolic/`. Your harness defines everything: tools, skills, roles, workflows, projects, and prompts.

## File Locations

| Path | Purpose |
|------|---------|
| `~/.hypergolic/main.py` | Your harness entry point — registers the built-in defaults and your customizations |
| `~/.hypergolic/prompts/` | Your custom prompts (including overrides of built-in role/skill prompts) |
| `~/.hypergolic/tools/`, `skills/` | Your custom tools and skills |
| `~/.hypergolic/projects/<id>/PROMPT.md` | Per-project prompts |
| `~/.hypergolic/pyproject.toml` | Python dependencies (managed by uv) |

The built-in tools, skills, roles, and prompts ship inside the installed `hypergolic` package and are loaded straight from it via `app.use_defaults()` — nothing is copied into `~/.hypergolic`. Everything under `~/.hypergolic` is yours to edit; `hypergolic update` only bumps the package version and regenerates `pyproject.toml`/`.gitignore`, never your files.

## The Harness (`main.py`)

Your harness is a Python script that creates an `App` instance, loads the built-in defaults, and customizes them:

```python
from hypergolic import App, Project

app = App()

# Register the built-in tools, roles, and skills (imported from the package).
app.use_defaults()

# Customize the defaults instead of forking them. A few examples:
# app.modify_role("generalist", remove_tools=["host_cmd"], add_skills=[my_skill])
# app.override_skill("history", prompt_path="~/.hypergolic/prompts/skills/history.md")
# app.override_tool("edit", approval=my_policy)
# app.remove_tool("command")

# Register your projects
project = Project(
    id="my-app",
    name="My App",
    description="A web application",
    git_root="/Users/me/code/my-app",
    prompt_path="~/.hypergolic/projects/my-app/PROMPT.md",
)
app.register_project(project)

if __name__ == "__main__":
    app()
```

When you run `h`, this script validates all registrations, runs database migrations, starts a FastAPI server, and opens the desktop UI.

## Projects

A project is a git repository the agent can work in. Register projects on the `App` to make them available in the UI:

```python
project = Project(
    id="my-app",
    name="My App",
    description="A web application",
    git_root="/Users/me/code/my-app",
    prompt_path="~/.hypergolic/projects/my-app/PROMPT.md",
)
app.register_project(project)
```

Tools, skills, and workflows registered on a project are only available in that project's sessions. Register on `app` for global availability.

### Pre-commit checks

Set `pre_commit` to gate every `git commit` on a check command:

```python
project = Project(..., pre_commit="bin/check")
```

Before committing, the git tool runs the command inside the project's sandbox (first declared container, at the workspace mount) and aborts the commit on nonzero exit, surfacing the command's output. It is fail-closed: if the sandbox is unavailable, the commit is refused rather than allowed through unchecked. The command never executes on the host, so it may safely invoke repo-defined scripts.

Because checks run centrally on every commit, steer the agent (in your project prompt) away from running tests, type checkers, or linters ad hoc — commit-time enforcement makes incremental runs redundant.

## System Prompt Assembly

The system prompt is assembled from multiple sources, concatenated in order:

1. **Role prompt** — The active role's prompt. Built-in role prompts ship in the installed `hypergolic` package; override one by pointing it at your own file (e.g., `app.override_role("generalist", prompt_path="~/.hypergolic/prompts/roles/generalist.md")`)
2. **User prompt** — Your personal prompt, if configured
3. **Project prompt** — Per-project guidance from `projects/<id>/PROMPT.md`
4. **Session context** — Auto-generated: session ID, working directory, OS, git branch, sandbox and mounts
5. **Command discovery** — A short pointer to `apropos` and `/tools`; the full command catalog stays on the filesystem instead of in the prompt
6. **Workflow context** — Workflow and state prompts, if a workflow is active

Each layer adds specificity. The role sets baseline behavior, user and project prompts add preferences and conventions, and the discovery pointer tells the agent how to find capability and expertise in `/tools` when it needs it.

### Prompt Sources

Prompts can be provided in three mutually exclusive ways (on any object that accepts them):

```python
# From a file
Role(id="reviewer", name="Reviewer", prompt_path="~/.hypergolic/prompts/roles/reviewer.md")

# Inline
Role(id="reviewer", name="Reviewer", prompt="You are a code reviewer. Focus on...")

# Dynamic (computed at runtime)
Role(id="reviewer", name="Reviewer", prompt_fn=lambda: generate_prompt())
```

### Example Role Prompt (`~/.hypergolic/prompts/roles/generalist.md`)

```markdown
You are a generalist coding assistant.

Communicate concisely.
Research before beginning a task.
Fix pre-existing errors or failures.
```

### Example Project Prompt (`~/.hypergolic/projects/my-app/PROMPT.md`)

```markdown
# My App

This is a Django 5.1 project using PostgreSQL.
Run `./bin/validate` after making changes to verify the build.
Never modify files in the `generated/` directory.
```

## App Options

The `App` constructor accepts a few top-level settings:

```python
from hypergolic import App, ModelTier, SsoConfig

app = App(
    truncate_token_threshold=50_000,               # Token limit before context truncation
    strip_history_thinking=True,                   # Drop thinking blocks from replayed history
                                                   # (per-role override: Role(strip_history_thinking=...))
    default_model_tier=ModelTier.MEDIUM,           # Default model tier for sessions
    knowledge_distillation=True,                   # Background knowledge capture (see below)
    turn_compaction_floor_tokens=5_000,            # Min turn size before per-turn compaction; 0 disables
    sso=SsoConfig(                                 # AWS SSO recovery for bedrock/mantle tiers
        auto_login=True,                           # Run `aws sso login` when the session expires
        login_timeout=180,                         # Seconds to wait for the browser login
        max_login_attempts=3,                      # Consecutive failures before giving up
    ),
)
```

`dispatch` can change four of these for one new session, on top of a harness pin:
`--strip-history-thinking=BOOL` (applies to every role too), `--truncate-token-threshold=N`,
`--turn-compaction-floor-tokens=N` and `--shape-grep-output=BOOL`. The values are stored in
`sessions.app_overrides`, so a resumed session keeps them. A session with overrides runs on a copy of
the App, so a harness reload during that session does not reach it.

### Knowledge distillation

Each project's `/shared/knowledge/` directory is a persistent knowledge base:
its index (`knowledge/README.md`) is injected into every session's system
prompt, and deeper topic files are read on demand. When a top-level session
concludes, Hypergolic dispatches a background researcher session (same model
tier) that explores the session's history and distills durable learnings — user
corrections and preferences, decisions, gotchas — into the base, curating as
it goes (see the `knowledge-base` skill). Set `knowledge_distillation=False`
to disable the background pass; the seeded knowledge base and prompt
injection remain.

## Viewing Config

From the UI, use the **Harness** panel in the left sidebar (`⌘/Ctrl + 4`) to see your current configuration, including registered tools, skills, roles, and projects.
