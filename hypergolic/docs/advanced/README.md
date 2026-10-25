# Advanced Usage

## Custom Tools

Custom tools are Python functions with typed inputs, structured outputs, and approval policies. A tool's availability depends on where you register it:

| Registered on    | Available when                  |
| ---------------- | ------------------------------- |
| `app`            | All sessions, always            |
| `project`        | Only in that project's sessions |
| `skill`          | Only when that skill is active  |
| `role`           | Only when that role is active   |
| `workflow_state` | Only during that workflow state |

### Defining Tools

A tool needs four things: an ID, a description (so the agent knows when to use it), an input schema, and a run function.

```python
from hypergolic import Tool, InputSchema, ToolResult, ToolContext

class ValidateInput(InputSchema):
    fix: bool = False

async def run_validate(inp: ValidateInput, ctx: ToolContext) -> ToolResult:
    import subprocess
    cmd = ["./bin/validate"]
    if inp.fix:
        cmd.append("--fix")
    # `working_directory()` is the session's worktree. Always use this for
    # subprocesses that touch project files — hardcoding a path will point
    # at the wrong checkout.
    cwd = str(ctx.session.working_directory())
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return ToolResult(
        content=[{"type": "text", "text": result.stdout + result.stderr}],
        is_error=result.returncode != 0,
    )

validate_tool = Tool(
    id="validate",
    name="Validate",
    description="Run the project's validation suite. Use --fix to auto-fix issues.",
    input_schema=ValidateInput,
    run=run_validate,
    approval="ALLOW",
)
```

### Session working directory

Tools that run subprocesses or touch the filesystem should use
`ctx.session.working_directory()` to find the correct cwd:

- In a normal session it returns the project's `git_root`.
- In a dispatched session with a worktree it returns the worktree path.

This lets a single tool definition work correctly whether the agent is
editing the main checkout or an isolated worktree. Hardcoding the project
path causes tests/lint/build commands to silently run against the wrong
checkout — newly written files appear missing, and edits aren't reflected.

Register it globally or on a specific project:

```python
# Available in all sessions
app.register_tool(validate_tool)

# Available only in this project
project.register_tool(validate_tool)
```

### Approval Policies

The `approval` field controls whether the user is prompted before the tool runs. It can be a string shortcut or a callable:

```python
from hypergolic import ToolApprovalDecision, ApprovalContext

# String shortcuts
tool = Tool(..., approval="ALLOW")              # Never ask
tool = Tool(..., approval="REQUIRE_APPROVAL")   # Always ask
tool = Tool(..., approval="DENY")               # Never run

# Dynamic approval based on input
def deploy_approval(ctx: ApprovalContext):
    if ctx.input.environment == "production":
        return ToolApprovalDecision(
            decision="REQUIRE_APPROVAL",
            context="Deploying to production",
        )
    return ToolApprovalDecision(decision="ALLOW")

tool = Tool(..., approval=deploy_approval)
```

### Tool Parameters

Define parameters as fields on your `InputSchema` subclass. Pydantic handles validation and type coercion:

```python
class DeployInput(InputSchema):
    environment: str = "staging"
    dry_run: bool = False
    timeout: int = 300
```

The schema is automatically converted to JSON Schema for the LLM.

### Skill-Gated Tools

Tools registered on a skill are only available when that skill is active:

```python
semgrep_tool = Tool(
    id="semgrep",
    name="Semgrep",
    description="Run semgrep security scan on the codebase",
    input_schema=SemgrepInput,
    run=run_semgrep,
)

security_skill = Skill(
    id="security-reviewer",
    name="Security Review",
    description="Review code for security vulnerabilities",
    prompt_path="~/.hypergolic/prompts/skills/security-reviewer.md",
    tools=[semgrep_tool],
)
app.register_skill(security_skill)
```

## MCP Servers

Hypergolic supports the [Model Context Protocol](https://modelcontextprotocol.io/) for connecting external tool servers. MCP servers expose their own tools that the assistant can invoke.

### Configuration

Register MCP servers in your `main.py`:

```python
# stdio transport (spawns a local process)
app.register_mcp_server(
    "my-server",
    transport="stdio",
    command="npx",
    args=["-y", "@my-org/mcp-server"],
)

# HTTP transport
app.register_mcp_server(
    "my-api",
    transport="streamable_http",
    url="https://my-server.example.com/mcp",
    auth={"type": "token", "token_env_var": "MY_SERVER_TOKEN"},
)

# SSE transport
app.register_mcp_server(
    "my-sse-server",
    transport="sse",
    url="https://my-server.example.com/sse",
)
```

### Supported Transports

| Transport         | Fields                   | Description                                               |
| ----------------- | ------------------------ | --------------------------------------------------------- |
| `stdio`           | `command`, `args`, `env` | Spawns a local process and communicates over stdin/stdout |
| `streamable_http` | `url`, `auth`            | Connects to an HTTP endpoint                              |
| `sse`             | `url`, `auth`            | Connects via Server-Sent Events                           |

### Authentication

For HTTP-based transports, configure auth with a token read from an environment variable:

```python
app.register_mcp_server(
    "my-server",
    transport="streamable_http",
    url="https://my-server.example.com/mcp",
    auth={
        "type": "token",
        "token_env_var": "MY_SERVER_TOKEN",
        "token_header": "Authorization",
        "token_prefix": "Bearer",
    },
)
```

### Managing MCP Servers

The assistant can use the `mcp` command to list, enable, and disable MCP servers during a session. You can also manage them from the UI.

## Skills

Skills are packages of on-demand expertise. Each one materializes as a directory in the sandbox's `/tools`: the skill's prompt becomes `<id>/README.md`, which the assistant reads when the topic comes up, and the skill's tools become commands on `PATH`. The session's prompt carries only a one-line description per skill, so a skill costs almost nothing until it is read.

### Defining Skills

```python
from hypergolic import Skill, Tool

query_tool = Tool(
    id="query-api",
    name="Query API",
    description="Query the platform API for data",
    input_schema=QueryInput,
    run=run_query,
)

platform_skill = Skill(
    id="platform-expertise",
    name="Platform Expertise",
    description="Deep knowledge of the platform architecture and APIs",
    prompt_path="~/.hypergolic/prompts/skills/platform.md",
    tools=[query_tool],
)
app.register_skill(platform_skill)
```

Nothing needs turning on: the assistant finds `platform-expertise` via `apropos` (or `/tools/index.md`) and runs `platform-expertise --help` (or reads `/tools/platform-expertise/README.md`) when the work calls for it.

### Prompt Sources

Like all prompt-bearing objects, skills accept `prompt_path`, `prompt`, or `prompt_fn` (mutually exclusive):

```python
# From a markdown file
Skill(id="debug", name="Debug", description="...", prompt_path="~/.hypergolic/prompts/skills/debug.md")

# Inline
Skill(id="debug", name="Debug", description="...", prompt="You are a debugging expert...")

# Dynamic
Skill(id="debug", name="Debug", description="...", prompt_fn=lambda: build_debug_prompt())
```

## Roles

Roles replace the base system prompt entirely. While skills are read on demand, a role changes the foundational behavior of the assistant.

### Defining Roles

```python
from hypergolic import Role

reviewer = Role(
    id="reviewer",
    name="Code Reviewer",
    prompt_path="~/.hypergolic/prompts/roles/reviewer.md",
    skills=[security_skill],   # Reachable in every session under this role
    tools=[ReviewTool],        # Scoped tools (`git` is already universal)
)
app.register_role(reviewer)
```

The `skills` field scopes which skills a session under this role can reach. The `tools` field scopes which tools are available under this role. The role's prompt is used _instead of_ the default role prompt.

The `cmd` (shell) tool is not a role tool — it comes from the project's sandbox (see [Project Sandboxes](#project-sandboxes)), so you don't declare it on a role.

## Project Sandboxes

A sandbox is the containerized environment the agent runs shell commands in for a project. It is the safety boundary: a command executes inside a disposable container, so a prompt injection cannot reach the host. Configure one with a typed `ProjectSandbox` and attach it with `project.configure_sandbox(...)`.

`Container.image` is either a registry ref string or an authored `Image`: `base` becomes the Dockerfile's `FROM`, `steps` are verbatim Dockerfile instructions, and `context` (only needed when steps `COPY` local files) anchors those paths. Hypergolic owns the frame around the steps — required agent tooling (uv) is inserted after them while still root, and `user`, when set, is emitted last — so workspace images always satisfy the toolchain contract. A plain registry ref on a `skip_workspace_mount` infra container (postgres below) is pulled verbatim.

```python
from hypergolic.sandbox.model import (
    ProjectSandbox, Container, Image, Port, Healthcheck, Volume, Egress,
)

sandbox = ProjectSandbox(
    id="my-project-sandbox",
    containers=[
        Container(
            id="api",
            image=Image(
                base="python:3.13-bookworm",
                steps=["RUN pip install --no-cache-dir fastapi uvicorn"],
            ),
            environment={"DATABASE_URL": "postgresql://username:password@postgres:5432/mydb"},
            depends_on=["postgres"],
            expose=[Port(container=8000, name="api")],
            healthcheck=Healthcheck(test="curl -f http://localhost:8000/health"),
        ),
        Container(id="frontend", image="node:22-bookworm",
                  depends_on=["api"], expose=[Port(container=5173, name="frontend")]),
        Container(id="postgres", image="postgres:16", skip_workspace_mount=True,
                  environment={"POSTGRES_USER": "username", "POSTGRES_PASSWORD": "password",
                               "POSTGRES_DB": "mydb"}),
    ],
    volumes=[Volume(id="pgdata", mounts={"postgres": "/var/lib/postgresql/data"})],
    egress=Egress.Allow(["https://pypi.org", "https://registry.npmjs.org"]),
)
project.configure_sandbox(sandbox)
```

`configure_sandbox` compiles the model to a Compose file under `~/.hypergolic/sandboxes/<id>.compose.yaml` (a generated, version-controlled asset) and registers the project's `cmd` tool.

### How it behaves

- **No default container.** The agent execs into any container. With more than one, the `cmd` tool takes a required `container` argument (a typed enum of the declared ids); with one, it is omitted.
- **Shared `/app` mount.** The session's git dir is bind-mounted read-write at `/app` in every container — one shared tree. An edit made from one container is visible in the others and in the host worktree.
- **Read-only `/harness` mount.** The user's harness (`~/.hypergolic`) is bind-mounted read-only at `/harness` in every container, so the agent can inspect its own configuration (and the installed source under `/harness/.venv`) when troubleshooting. Activate the `troubleshooting` skill for guidance. Credentials and worktrees live _outside_ the harness in `~/.hypergolic_internals/` (`tokens/`, `worktrees/`) precisely so they are never exposed through this mount.
- **Dynamic ports.** `Port(container=N, name=...)` allocates a free host port per session (no collisions across concurrent sessions). The resolved endpoint is surfaced in the session context as `name http://localhost:<port>`.
- **Resource limits.** `Container(cpus=4, mem_limit="2g")` caps one container (Compose `cpus` / `mem_limit`). Unset means no limit, so one busy session can use every host core. A CPU quota does not change `nproc`, so the quota is also exported as `HG_CPUS` (rounded up); size test workers from it (`pytest -n "${HG_CPUS:-auto}"`). Past `mem_limit` the kernel OOM-kills, so cap JVM heaps (`-Xmx`) below it.
- **Project-level egress.** A single `Egress` policy is the agentic-escape boundary, enforced by a Squid proxy with domain-level allowlisting. `DenyAll` (default) blocks outbound; `Allow([...])` permits listed domains; `AllowAll` is unrestricted. Egress does not affect inter-container traffic — services always reach each other by name.

The `harness-sandbox` skill (under `harness-engineering`) helps author and reason about sandboxes, including dev-image, hot-reload, egress, and build-caching advice.

## Browser Automation

The `browser` tool provides headless Chrome automation via [rodney](https://github.com/nichochar/rodney). The assistant can:

- Navigate to URLs, click elements, fill forms
- Take screenshots and PDFs
- Execute JavaScript
- Read page text, HTML, and accessibility trees
- Wait for load states and network idle

Useful for testing web apps, scraping, and verifying UI changes.

## Session History

The assistant can search across past sessions using the `history` tool, which runs read-only SQL against the Hypergolic Postgres database. It can query `pg_tables` or `information_schema.columns` to discover the schema, then join across `sessions`, `messages`, `artifacts`, and related tables. Useful for recalling previous conversations, finding how a problem was solved before, or continuing interrupted work.

## Headless Runs (`hypergolic run`)

Drive one agent turn from the shell, no UI attached:

```bash
hypergolic run --project my-project --model-tier EXTRA_HIGH \
    --message "Reply back with hello world"
```

The command loads your harness (`~/.hypergolic/main.py`) fresh in its own
process, so it exercises uncommitted prompt/tool/config edits _before_ you
restart the long-running server — ideal for smoke-testing harness changes.
The session is a normal one (own worktree + sandbox, visible in the UI and
history afterwards), with two differences:

- **Approvals auto-deny.** There is no human attached; approval-gated tool
  calls are denied with guidance, like dispatched child sessions.
- **One turn per invocation.** The final `end_turn` content is printed;
  everything else is queryable in history.

By default the worktree and sandbox are torn down after the turn. Keep them
alive to iterate:

```bash
hypergolic run --project my-project --no-conclude -m "Look at src/foo.py"
# Session (CX...)
hypergolic run --session CX... -m "Now refactor it"          # follow-up turn
hypergolic run --session CX... -m "Thanks, done" --conclude  # tear down
```

`--json` emits machine-readable output (`session_id`, `outcome`, `content`,
`stop_reason`); the exit code is non-zero when the turn errors. `--model-tier`
defaults to HIGH, `--base-branch` to the project's current branch, and
`--content-json` accepts a content-block list when plain `--message` text
isn't enough.

## Tips for Effective Prompt Engineering

The prompts you write for roles, skills, projects, and workflow states are the primary way you shape your assistant's behavior. Here are some guidelines:

### Writing Role Prompts

Role prompts set the foundational persona. Be specific about:

- **Communication style** — Concise vs. detailed? Formal vs. casual? Should it explain its reasoning?
- **Behavioral constraints** — What should it always or never do? (e.g., "Always run tests before committing," "Never modify generated files")
- **Decision-making approach** — Should it ask before acting, or be autonomous? When should it escalate?
- **Tool preferences** — Which tools should it favor or avoid?

```markdown
# Code Reviewer

You are a thorough code reviewer. Focus on correctness, maintainability, and test coverage.

- Read the full diff before commenting
- Flag potential bugs, not style preferences
- Suggest specific fixes, not vague advice
- If tests are missing for changed code, say so
- Never modify files directly — only comment on what should change
```

### Writing Skill Prompts

Skill prompts inject domain expertise. They should be:

- **Focused on a specific domain** — What does this expertise cover?
- **Actionable** — What should the assistant do differently when this skill is active?
- **Tool-aware** — If the skill includes tools, explain when and how to use them

```markdown
# Database Migration Expertise

You have deep expertise in database migrations and schema design.

- Always check for existing migrations before creating new ones
- Prefer reversible migrations
- Consider data migration needs alongside schema changes
- Use the `db-validate` tool to check migration consistency
- Warn about migrations that lock tables on large datasets
```

### Writing Project Prompts

Project prompts encode conventions specific to a codebase. Cover:

- **Tech stack** — Languages, frameworks, key libraries, versions
- **Project structure** — Where things live, naming conventions
- **Testing approach** — How to run tests, coverage requirements, testing patterns
- **Things to avoid** — Deprecated patterns, files not to touch, common pitfalls

```markdown
# My App

## Stack

Python 3.14, FastAPI, SQLAlchemy, Alembic, Pydantic 2.x
Tests: pytest, 100% coverage required
Lint: ruff | Types: ty

## Conventions

- Run `bin/check` before committing (lint + type check + tests)
- Never edit files in `src/app/generated/`
- All API endpoints need OpenAPI descriptions
- Use `uv` for package management, never pip
```

### Writing Workflow State Prompts

Workflow state prompts should be **self-contained**. When `truncate_on_entry` is true, the agent loses prior conversation and only has artifacts and the state prompt:

- **Explain the phase** — What is this step trying to accomplish?
- **Reference artifacts** — Tell the agent which artifacts from prior states it has and how to use them
- **Define the output** — What should the structured output contain? What makes a good vs. bad output?
- **Explain transitions** — When to use success vs. failure vs. suppressed

```markdown
# Implementation Planning

You have a PRD artifact from the requirements phase. Your job is to produce an implementation plan.

1. Read the PRD carefully
2. Identify the key files that need to change
3. Break the work into ordered steps
4. For each step, note what changes and what tests to write

Use `workflow_transition_success` when the plan is complete.
Use `workflow_transition_failure` if the PRD is unclear or contradictory.
```

### Iterating on Prompts

- **Conclude sessions with feedback.** Your ratings and notes are the primary signal for spotting patterns in what works and what doesn't.
- **Start specific, then generalize.** Write prompts for a specific task first, then extract reusable patterns.
- **Watch tool usage.** If the assistant isn't using the right tools or is using them poorly, your prompt probably needs to be more explicit about tool selection.
