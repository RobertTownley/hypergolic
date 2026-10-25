from hypergolic.contrib.tools.mcp_command.actions import approve_mcp, mcp_eval_behavior, run_mcp
from hypergolic.contrib.tools.mcp_command.parse import McpInput, McpOutput, parse_mcp
from hypergolic.harness.primitives.results import CommandExample
from hypergolic.harness.primitives.tool import HOST, Tool

mcp_command = Tool(
    id="mcp",
    tags=["mcp", "model-context-protocol", "external-tool", "server", "integration", "vendor"],
    name="MCP",
    description=(
        "Reach an MCP server's tools: list servers, activate one, print a tool's "
        "input schema, then call it."
    ),
    usage=(
        "mcp list | mcp activate <server> | mcp deactivate <server> | "
        "mcp schema <server> <tool> | mcp exec <server> <tool> [--flag=value ...]; "
        "quote-heavy values: --flag @- with the value in a quoted heredoc"
    ),
    guidance=(
        "A server's tools are runtime data, so read them rather than assuming: "
        "`mcp list` for what exists, `mcp schema` for the arguments a tool "
        "accepts. Activating a server also puts one command per tool on PATH as "
        "`mcp.<server>.<tool>`, so `mcp exec` and that command are the same call "
        "by two spellings. "
        "Flags map to the schema's own field names, in either spelling, and the "
        "schema also types them: a field declared a string keeps its text, so a "
        "`--reply_ts=1700000000.000100` stays exact, while anything else is "
        "parsed as JSON when it can be, making `--limit=5` a number and "
        "`--ids='[1,2]'` a list; pass a whole JSON object as a bare argument "
        "when flags cannot express it. Activation is per session and "
        "only affects which servers this session treats as active — it never "
        "changes the tools offered over the wire; deactivating the last session "
        "using a server also closes the connection, so `mcp deactivate X && mcp "
        "activate X` is the way to replace a session that has gone bad."
    ),
    input_schema=McpInput,
    output_schema=McpOutput,
    examples=[
        CommandExample(
            command="mcp list | jq -r '.[] | select(.status == \"active\") | .server'",
            note="Which servers this session is already using.",
        ),
        CommandExample(
            command="mcp activate analytics && mcp schema analytics query_chart",
        ),
        CommandExample(
            command="mcp exec analytics query_chart --chart-id=abc123 | jq '.series'",
        ),
    ],
    domain=HOST,
    approval=approve_mcp,
    eval_behavior=mcp_eval_behavior,
    parse=parse_mcp,
    run=run_mcp,
)
