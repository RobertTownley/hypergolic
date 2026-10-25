# Skill: Harness Engineering

This skill covers changing the user's instance of Hypergolic itself.

Hypergolic is a Python framework for building and customizing agentic coding assistants ("Harnesses"). It's what's driving your session. Configuration is Python objects for projects, skills, tools, and workflows. `uv tool install hypergolic` installs it on the user's host; `hypergolic init` creates a git repo at `~/.hypergolic`.

## Principles

### Efficiency
Hypergolic uses advanced models by default, and running it is expensive. Pursue token efficiency wherever it's unlikely to hurt quality.

### Progressive Disclosure
Other harnesses give agents too much context (bloated prompts, degraded attention) or too little (agents re-learn the same facts every session). Keep always-on context minimal; make everything else discoverable on demand — `apropos` to find capability, `activate_skill` to load it, subskills for depth.

### Quality
Current convention isn't necessarily right: agents bloat projects over time with shortcuts and misunderstandings. The Harness is itself an important project — keep it well-organized, well-tested, and documented within token-efficiency reason. Prefer directories of small files over large files, simple composable functions over large operations. Refactor frequently and liberally.

### Ongoing Improvement
Hypergolic stores all content and operations in a database queryable via the `history` command — a ledger of what agents did well and struggled with. When the user gives feedback on how the agent operates, capture it durably.

## Components
Definitive signatures live in the source: `/hypergolic/harness/primitives/` (Tool, Skill, Role, Workflow), `/hypergolic/harness/project.py`, `/hypergolic/sandbox/model.py` (ProjectSandbox). Read them before authoring — never restate or guess an API.

- **Project** — top-level component; each maps to a git repo on the user's host
- **Tool** — an operation the agent invokes; may execute on the host. Carries an input schema, an approval policy, and a description + tags searched by `apropos`. Good candidates: external API calls, anything needing credentials the sandbox lacks, actions the user repeatedly asks for
- **Skill** — a container for specialized information. Activation delivers the prompt and names the skill's tools and subskills, so knowledge layers: e.g. a roadmap skill outlining structure, a subskill per initiative; a frontend skill with conventions, subskills for CSS, hooks, SSR
- **MCP** — external MCP servers, app-wide or per-project
- **Sandbox** — the containers a project's sessions run in
- **Prompt** — role, skill, and system text the agent reads

Activate the building block's skill before working with it: `creating-skills`, `harness-mcp`, `harness-sandbox`, `writing-prompts`

### Where capability should live
- **Harness tool** (`/harness`, user-provided): needs host access, credentials, or an approval gate
- **/shared script** (agent-authored): runs in the sandbox, evolves freely across sessions; a header comment + `tags:` line makes it apropos-searchable
- **Skill**: knowledge rather than execution — guidance that shouldn't cost tokens until needed

## Sandbox
The agent's execution environment; most productive work should happen inside it. Pre-bake needs at image build time (package managers installed, dependencies pre-warmed, venvs pre-built); instantiate per-session dependencies (databases, caches) alongside the code with env vars supporting immediate use. `activate_skill harness-sandbox` for configuration.

### /shared
All sessions share a rw mount at /shared. Maintain it for incremental discovery — e.g. /shared/docs/* for durable learnings and prior initiatives, /shared/scripts/* for reusable operations. Prune stale content when you find it.

## Changing the Harness

### Process
On session startup your sandbox gets its own clone of `~/.hypergolic`, mounted rw at /harness. Edit and commit there with ordinary git, then `git push origin main` from /harness: the push runs the harness's merge gates (the user's approval by default) and lands a squash of your commits on main. Landed changes go live after `reload_harness`, which rebuilds the App from ~/.hypergolic in place; other sessions keep running and your own turn continues. `restart` (full process, interrupts every session) is only for edits to the hypergolic package itself.

Validate edits with `validate_harness` before merging.

### Proposals queue
Concluding-time distillation sessions file harness-improvement ideas in
`/shared/harness/proposals/*.md` (they can't push /harness changes themselves).
Triage when you're in here: implement, fold into a better design, or delete
stale ones — the file is the ticket, so remove it once resolved.

### Fine-Tuning
Author new tools, skills, prompts, roles, and workflows. Refine built-ins by reading Hypergolic source and using the override API in main.py — `app.override_tool()`, `app.modify_role()`, `app.override_skill()`, `app.remove_tool()`. If a customization you want isn't supported, name that limitation to the user explicitly.
