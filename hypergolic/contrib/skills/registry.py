from hypergolic.contrib import contrib_path
from hypergolic.contrib.tools.history import history_tool
from hypergolic.contrib.tools.mcp_command import mcp_command
from hypergolic.contrib.tools.git_sync import git_fetch_tool
from hypergolic.contrib.tools.pull_request import pull_request_tool
from hypergolic.contrib.tools.readiness import readiness_probes_tool
from hypergolic.contrib.tools.review import ReviewTool
from hypergolic.contrib.tools.traces import traces_tool
from hypergolic.contrib.tools.registry import HARNESS_ENGINEER_TOOLS
from hypergolic.harness.primitives.bundles import Skill

harness_mcp_skill = Skill(
    id="harness-mcp",
    tags=["mcp", "model-context-protocol", "server", "approval-policy", "integration"],
    name="Harness MCP",
    description="Configure MCP servers and write an mcp_approval_policy to auto-approve safe calls while keeping destructive operations gated",
    prompt_path=contrib_path("prompts/skills/harness-mcp.md"),
)

manage_mcp_skill = Skill(
    id="mcp",
    tags=["mcp", "model-context-protocol", "external-tool", "server", "integration", "vendor"],
    name="Manage MCP Servers",
    description="List, enable, or disable MCP servers for this session",
    # One command whose subcommands read a server's tool list at call time, so
    # enabling a server changes files in /tools rather than anything the model
    # was sent — the prompt prefix stays cached.
    tools=[mcp_command],
)

history_skill = Skill(
    id="history",
    tags=["sql", "database", "analytics", "telemetry", "sessions", "transcripts",
        "approvals", "usage", "evidence"],
    name="History",
    description="Read-only SQL access to Hypergolic's own DB (sessions, messages, tool_approvals, …)",
    tools=[history_tool],
)

harness_performance_investigating_skill = Skill(
    id="harness-performance-investigating",
    tags=["slow", "latency", "bottleneck", "trace", "traceql", "logql", "promql",
        "tool-calls", "database", "sql", "sandbox", "stall"],
    name="Investigating Harness Performance",
    description="Find why a session, turn, tool call, or DB query is slow, or why a telemetry signal is missing",
    prompt_path=contrib_path("prompts/skills/harness-performance-investigating.md"),
)

harness_performance_instrumenting_skill = Skill(
    id="harness-performance-instrumenting",
    tags=["instrument", "span", "opentelemetry", "otel", "log-context", "custom-tool"],
    name="Instrumenting the Harness",
    description="Add spans or log context to your own tools or to Hypergolic source, and check they arrive",
    prompt_path=contrib_path("prompts/skills/harness-performance-instrumenting.md"),
)

harness_performance_skill = Skill(
    id="harness-performance",
    tags=["performance", "slow", "latency", "telemetry", "tracing", "opentelemetry",
        "grafana", "profiling", "tool-calls", "database"],
    name="Harness Performance",
    description="See where Hypergolic spends time — sessions, turns, model calls, tools, sandbox commands, DB — from its own traces, logs, and metrics",
    prompt_path=contrib_path("prompts/skills/harness-performance.md"),
    tools=[traces_tool],
    skills=[harness_performance_investigating_skill, harness_performance_instrumenting_skill],
)

harness_checkup_skill = Skill(
    id="harness-checkup",
    tags=["checkup", "verify", "readiness", "probe", "scorecard", "end-to-end",
        "sandbox", "hang", "broken", "diagnose"],
    name="Harness Checkup",
    description="Verify a project's harness works end-to-end (tiered readiness probes with a scorecard) and diagnose sandboxes that hang, fail to start, or misbehave",
    prompt_path=contrib_path("prompts/skills/harness-checkup.md"),
    tools=[readiness_probes_tool],
)

harness_sandbox_skill = Skill(
    id="harness-sandbox",
    tags=["sandbox", "container", "docker", "mount", "port", "egress", "compose"],
    name="Harness Sandbox",
    description="Configure a project's containerized sandbox — the ProjectSandbox model, the container exec model, the /app mount, dynamic exposed ports, and project-level egress",
    prompt_path=contrib_path("prompts/skills/harness-sandbox.md"),
)

troubleshooting_skill = Skill(
    id="troubleshooting",
    tags=["troubleshoot", "diagnose", "broken", "misbehaving", "harness", "fix",
        "self-repair"],
    name="Troubleshooting",
    description="Diagnose and durably fix your own tools, sandbox, or configuration. Activate when your tools don't work as expected",
    prompt_path=contrib_path("prompts/skills/troubleshooting.md"),
)

writing_prompts_skill = Skill(
    id="writing-prompts",
    tags=["prompt", "system-prompt", "instruction", "token-budget", "rewrite",
        "description", "tags"],
    name="Writing Prompts",
    description="Author or revise any prompt content \u2014 token policing, retrieval-friendly descriptions and tags, keeping prompts true",
    prompt_path=contrib_path("prompts/skills/writing-prompts.md"),
)

writing_skill_prompts_skill = Skill(
    id="writing-skill-prompts",
    tags=["subskill", "progressive-disclosure", "split", "structure"],
    name="Writing Skill Prompts",
    description="Shape a skill's prompt so agents read only the branch they need: parent maps, sub-skills per path",
    prompt_path=contrib_path("prompts/skills/writing-skill-prompts.md"),
)

creating_skills_skill = Skill(
    id="creating-skills",
    tags=["skill", "create-skill", "author", "register", "subskill"],
    name="Creating Skills",
    description="Create, register, or override a skill and nest sub-skills",
    prompt_path=contrib_path("prompts/skills/creating-skills.md"),
    skills=[writing_skill_prompts_skill],
)

harness_engineering_skill = Skill(
    id="harness-engineering",
    tags=["harness", "configure", "tool", "skill", "role", "workflow", "project", "prompt",
        "self-improvement"],
    name="Harness Engineering",
    description="Change your instance of Hypergolic itself \u2014 tools, skills, roles, workflows, prompts, sandboxes, and projects",
    prompt_path=contrib_path("prompts/skills/harness-engineering.md"),
    tools=HARNESS_ENGINEER_TOOLS,
    skills=[
        harness_mcp_skill,
        harness_sandbox_skill,
        harness_checkup_skill,
        writing_prompts_skill,
        creating_skills_skill,
    ],
)

product_management_skill = Skill(
    id="product-management",
    tags=["prd", "requirements", "scope", "product", "planning", "user-story", "spec"],
    name="Product Management",
    description="Collaborate on requirements, challenge assumptions, define scope, and produce a PRD before implementation begins",
    prompt_path=contrib_path("prompts/skills/product-management.md"),
)

security_review_skill = Skill(
    id="security-review",
    tags=["security", "vulnerability", "injection", "auth", "owasp", "data-exposure"],
    name="Security Review",
    description="Analyze changes for security vulnerabilities: injection, auth gaps, data exposure, OWASP Top 10",
    prompt_path=contrib_path("prompts/skills/security-review.md"),
)

performance_review_skill = Skill(
    id="performance-review",
    tags=["performance", "latency", "profiling", "bottleneck", "optimization"],
    name="Performance Review",
    description="Evaluate changes for runtime performance, algorithmic complexity, N+1 queries, memory usage, and scalability",
    prompt_path=contrib_path("prompts/skills/performance-review.md"),
)

code_conventions_skill = Skill(
    id="code-conventions",
    tags=["convention", "style", "idiom", "codebase-norms"],
    name="Code Conventions",
    description="Check pattern consistency, appropriate DRY, and adherence to the codebase's existing conventions",
    prompt_path=contrib_path("prompts/skills/code-conventions.md"),
)

code_complexity_skill = Skill(
    id="code-complexity",
    tags=["complexity", "refactor", "simplify", "abstraction", "over-engineering"],
    name="Code Complexity",
    description="Spot excessive cyclomatic/cognitive complexity, deep nesting, long functions, and suggest simplification patterns",
    prompt_path=contrib_path("prompts/skills/code-complexity.md"),
)

conducting_simulations_skill = Skill(
    id="conducting-simulations",
    tags=["eval", "simulation", "replay", "conduct", "mock", "approval"],
    name="Conducting Simulations",
    description=(
        "Play the user and every conducted tool call in a running --eval child: "
        "reply, approve, mock, deny, or run the call yourself and send back the result"
    ),
    prompt_path=contrib_path("prompts/skills/conducting-simulations.md"),
    tools=[history_tool],
)

evaluation_skill = Skill(
    id="evaluation",
    tags=["eval", "simulation", "replay", "benchmark", "model-comparison", "agent-performance"],
    name="Evaluation",
    description=(
        "Conduct a simulated session: dispatch a child at past repo shas, "
        "play the user and every gated tool, then compare it with the "
        "source session. Read to test whether a harness change would have "
        "changed how a past task went."
    ),
    prompt_path=contrib_path("prompts/skills/evaluation.md"),
    tools=[history_tool],
    skills=[conducting_simulations_skill],
)

orchestration_skill = Skill(
    id="orchestration",
    tags=["dispatch", "subagent", "child", "parallel", "delegate", "merge", "approval", "conduct"],
    name="Orchestration",
    description=(
        "Split work across child sessions: dispatch them, answer their approval "
        "requests (approve, deny, escalate, mock), merge their work into your "
        "branch, and conclude them"
    ),
    prompt_path=contrib_path("prompts/skills/orchestration.md"),
    skills=[evaluation_skill],
)

git_pr_skill = Skill(
    id="git-pr",
    tags=["pull-request", "pr", "github", "publish"],
    name="Git: Pull Requests",
    description="Publish landed work to GitHub as a pull request. Activate when the user asks for a PR",
    prompt_path=contrib_path("prompts/skills/git-pr.md"),
)

git_repos_skill = Skill(
    id="git-repos",
    tags=["shared", "harness", "commit", "push", "persist", "repos"],
    name="Git: /shared and /harness",
    description="Commit and push in /shared and /harness, the sandbox's other two git repos",
    prompt_path=contrib_path("prompts/skills/git-repos.md"),
)

shared_skill = Skill(
    id="shared",
    tags=["shared", "persist", "scripts", "reusable", "commit", "push"],
    name="/shared",
    description="Persist scripts and knowledge across sessions in /shared, and commit and push them",
    prompt_path=contrib_path("prompts/skills/shared.md"),
)

images_skill = Skill(
    id="images",
    tags=["image", "screenshot", "png", "plot", "render", "see", "view", "attach"],
    name="Images",
    description="Look at an image in the sandbox (screenshot, plot, render) by attaching it to your tool result",
    prompt_path=contrib_path("prompts/skills/images.md"),
)

git_skill = Skill(
    id="git",
    tags=["land", "merge", "pull-request", "pr", "branch", "commit", "version-control", "finish", "done"],
    name="Git",
    description="Land finished work on a branch on the user's machine; publish it as a PR. Activate when a task is done",
    prompt_path=contrib_path("prompts/skills/git.md"),
    # `git` itself is universal (contrib/tools/registry.py); restating it here
    # would give a generalist session a second source for the id, and the skill
    # copy would silently beat an app-level `override_tool("git", ...)`.
    tools=[ReviewTool, git_fetch_tool, pull_request_tool],
    skills=[git_pr_skill, git_repos_skill],
)

knowledge_base_skill = Skill(
    id="knowledge-base",
    tags=["knowledge", "memory", "facts", "distill", "curate", "learnings",
        "preferences", "documentation"],
    name="Knowledge Base",
    description="Capture and curate durable project/user knowledge in /shared/knowledge — what to record, how to keep it modular, discoverable, and current",
    prompt_path=contrib_path("prompts/skills/knowledge-base.md"),
)

REVIEWER_SKILLS = [
    security_review_skill,
    performance_review_skill,
    code_conventions_skill,
    code_complexity_skill,
]

# The git skill is generalist-scoped (see contrib/roles/registry.py):
# `pull_request` lives only inside it. A child's `git push origin HEAD:<base>`
# lands only into its parent's sandbox (git/parent_land.py), with the parent's
# approval; it cannot move a host branch or publish on its own.
ALL_CONTRIB_SKILLS = [
    knowledge_base_skill,
    shared_skill,
    images_skill,
    troubleshooting_skill,
    harness_engineering_skill,
    manage_mcp_skill,
    history_skill,
    harness_performance_skill,
    orchestration_skill,
]
