# Tools

Hypergolic gives the assistant one tool over the wire: `cmd`, a shell in the project's sandbox container. Everything else — git, review, MCP, your own Python tools — is materialized as a *command* in the sandbox's `/tools` directory and invoked from that shell, the way a developer invokes anything else.

## The Command Surface

`/tools` is generated fresh each turn from the commands the session can reach:

```
/tools/index.md          one line per command: name and when to reach for it
/tools/<name>/README.md  what `<name> --help` prints — usage, arguments, approval posture
/tools/<name>/source     symlink to the implementation, so it cannot drift
/tools/bin/<name>        the executable shim; absent when the command is documentation only
```

`/tools/bin` is on `PATH`, so `git log --oneline -5` and `pull_request list` are ordinary shell invocations that compose with pipes and redirection. A shim posts its argv back to the harness, which parses it into the tool's typed input and applies the tool's approval policy — so approvals, approval views, and tool code are identical whether a command is invoked by name or wrapped by a script.

Skills that ship only guidance materialize as a directory with a README and no shim: documentation the assistant reads on demand.

The system prompt carries only a pointer to `apropos` and `/tools` — no per-command listing and no schemas. Discovery is a `--help` away instead of a catalog on every request, which keeps the prompt short, stable and cacheable for the whole session.

`apropos <what you are trying to do>` is the way from a task back to a command: it searches every declaration's tags, guidance and examples, and prints the whole index when nothing matches, so no capability becomes undiscoverable by being badly described. Tools and skills carry `tags` for exactly this: the words someone reaches for before they know the command exists.

## Built-in Commands

| Command | Description | Requires Approval |
|---------|-------------|-------------------|
| `git` | One git subcommand per call | Read-only/additive: No; destructive: Yes |
| `review` | Dispatch a reviewer over the branch's diff | No |
| `land` | Broker behind `git push origin HEAD:<branch>`: gates, then lands the pushed commits on that host branch (created at the fork point if new) — squashed by default, or fast-forwarded as-is with `land_mode="fast-forward"` / `git push -o mode=fast-forward`. A fast-forwarded merge commit (e.g. a sync merge of main into a PR branch) is gated on its own conflict resolutions, not on every commit it brings in; the merge-review UI offers the full range behind a toggle | No (gates may require approval) |
| `git_fetch` | Fetch GitHub state (branches, PR heads) into the host repo | No |
| `pull_request` | `list` / `view` GitHub PRs; `publish <branch>` pushes a host branch as it is and opens or updates its draft PR; it fails before approval unless the sandbox HEAD matches that branch (it fast-forwards the sandbox when the host is only ahead) | `publish`: Yes; `list`/`view`: No |
| `dispatch` | Run a child session under another role | No |
| `history` | Read-only SQL over past sessions, messages, and related tables | No |
| `mcp` | List, enable, or disable MCP servers, and call their tools | Varies by policy |
| `host_cmd` | Run a command on the host, outside the sandbox | Yes |
| `activate_skill` | Load a skill's context, tools, and subskills | No |
| `validate_harness` | Type-check and validate the harness config | No |
| `reload_harness` | Rebuild the App from `~/.hypergolic` in place; no restart, other sessions unaffected | No |
| `restart` | Restart the whole server process (needed only for changes to the hypergolic package) | Yes |

File reading, editing, and search are plain shell (`cat`, `sed`, `git grep`) inside the sandbox.

## How Tool Approval Works

Tools that modify your filesystem or execute arbitrary commands require explicit approval. When the assistant wants to use one, you'll see an approval prompt with the full details of what it wants to do.

You can:
- **Approve** (`Y`) — Let the tool run
- **Deny** (`N`) — Block the tool silently
- **Deny with message** (`D`) — Block and explain why
- **Configure** (`C`) — Open a harness session to configure an approval policy for this tool

### Configuring Approval Policies

Approval behavior is defined in Python when you register a tool. Each tool's `approval` field can be a string shortcut (`"ALLOW"`, `"DENY"`, `"REQUIRE_APPROVAL"`) or a callable that decides dynamically based on the input:

```python
from hypergolic import Tool, ToolApprovalDecision, ApprovalContext

def git_approval(ctx: ApprovalContext):
    read_only = ["status", "diff", "log", "show", "branch"]
    if any(ctx.input.args.startswith(cmd) for cmd in read_only):
        return ToolApprovalDecision(decision="ALLOW")
    return ToolApprovalDecision(decision="REQUIRE_APPROVAL")

git_tool = Tool(
    id="git",
    name="Git",
    description="Run git commands",
    input_schema=GitInput,
    run=run_git,
    approval=git_approval,
)
```

### Validation Before Approval

A tool can also set `validate_tool_call`: an `async (input, ctx) -> ValidationResult` that runs before the approval policy. `ValidationResult.invalid(message)` fails the call at once, with no prompt. `ValidationResult.valid(message)` lets the call continue, and the harness adds `message` to the tool result. It is separate from `approval`, so a changed policy never removes the check. `pull_request publish` uses it to require that the sandbox matches the host branch.

To publish PRs without a prompt, keep the check and change only the policy:

```python
app.override_tool("pull_request", approval="ALLOW")
```

To change how approval works for a tool, either edit the tool registration in `~/.hypergolic/main.py` directly, or press `C` during an approval prompt to open a harness engineering session.

## Tool Scoping

Where a tool is registered decides which sessions materialize it:

| Registered on | Available when |
|---------------|----------------|
| `app` | All sessions, always |
| `project` | Only in that project's sessions |
| `skill.tools` | Only in sessions that can reach that skill (app, project, role, or workflow scope) |
| `role.tools` | Only under that role |
| `workflow_state.tools` | Only while that workflow state is current |

A skill does not gate its tools behind an activation step: if a session can reach the skill, its commands are on `PATH` and its guidance is in `/tools`. The set changes only when the session's *scope* changes — entering a workflow state, enabling an MCP server — and `/tools` is rewritten on disk rather than in the prompt.

## Custom Tools

You can define your own tools as Python functions with typed inputs, structured outputs, and approval policies. See [Advanced Usage](advanced-usage.md#custom-tools) for the full pattern.

## MCP Tools

Tools from connected MCP servers appear alongside built-in tools. See [Advanced Usage](advanced-usage.md#mcp-servers).
