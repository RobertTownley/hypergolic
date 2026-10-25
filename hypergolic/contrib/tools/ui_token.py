"""Mint a read-only UI token so the agent can watch its own Hypergolic UI.

The token passes GET/HEAD API calls and spectator websockets only — approvals,
and turns require the real session cookie the pywebview
window holds. See hypergolic.auth for the token model.
"""

from hypergolic.auth import mint_readonly_token
from hypergolic.config.settings import settings
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import CommandExample, InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext


class MintUITokenInput(InputSchema):
    pass


async def mint_ui_token(inp: MintUITokenInput, ctx: ToolContext) -> ToolResult:
    token = mint_readonly_token(ctx.session.id)
    url = f"http://host.docker.internal:{settings.HYPERGOLIC_PORT}"
    return ToolResult.text(
        f"Read-only UI token minted, scoped to this session (one active token "
        f"per install: any session minting revokes the previous one).\n"
        f"url: {url}\n"
        f"cookie: h_token={token}\n"
        f"Read-only: GET/HEAD and spectator websocket for this session's data "
        f"only; other sessions' content, and mutations are denied."
    )


mint_ui_token_tool = Tool(
    id="mint_ui_token",
    tags=["ui", "browser", "screenshot", "spectate", "playwright", "token"],
    name="Mint UI Token",
    description="Mint a session-scoped read-only token for the live Hypergolic UI/API",
    input_schema=MintUITokenInput,
    run=mint_ui_token,
    approval=always("ALLOW"),
    examples=[
        CommandExample(
            command="mint_ui_token",
            note="then drive the UI headless, e.g. via playwright with the h_token cookie",
        ),
    ],
)
