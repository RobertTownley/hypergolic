Configure MCP servers in `main.py` and write an `mcp_approval_policy` that auto-approves safe calls without weakening security.

## Registering servers
`app.register_mcp_server(name, transport=..., ...)` — signature and options in `/hypergolic/harness/app/` source. Transports: `streamable_http`, `sse`, `stdio`. Auth: `none`, `token` (reads `token_env_var`), `oauth` (browser login).
Always set `description=` (what it reaches, in task words) and `tags=`: before activation a server lists no tools, so these are all `mcp list` and `apropos` can show.
A server that hides `<toolset>__<tool>` tools behind one switch tool taking `{toolset: true}` flags: set `toolset_switch="<tool>"`. `mcp exec` then enables a missing toolset itself and keeps every toolset in use, so skills need no enable step.

## Policy
Without a policy every MCP call requires approval — safe but noisy. Assign `app.mcp_approval_policy = fn(ctx: MCPApprovalContext) -> ToolApprovalDecision`; ctx carries `server`, `tool`, `input`, and `session` (branch on role to tighten/loosen). Return `ALLOW`, `REQUIRE_APPROVAL`, or `DENY`. A raising policy falls back to `REQUIRE_APPROVAL`.

The question is never "how often do I approve this?" — it's **"do I trust the agent to run this unattended, always?"**
- Auto-allow: read-only calls whose worst case is stale or missing data
- Gate: anything creating/updating/deleting external state, moving data between systems, or touching billing/access/permissions
- When in doubt, gate — friction is cheaper than an unattended write

Prefer one policy function with named sets of allowed tools over `if/elif` chains; verify tool names against the server's actual list (MCP panel in the UI).

## Approach
1. Identify registered servers; enumerate each server's tools (MCP panel, or ask)
2. Classify read vs write; ask what the user trusts unattended
3. Write the policy, assign in `main.py`, `validate_harness`, then `reload_harness`
