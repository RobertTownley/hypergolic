"""Swap the live App for one rebuilt from ~/.hypergolic — no process restart.

Most harness work (tools, prompts, skills, projects, roles) lives entirely
under ~/.hypergolic, and :func:`reload_live_harness` can re-exec that tree in
place. In-flight turns finish on the App they started with; every session's
next turn sees the new one. Changes to the ``hypergolic`` package itself are
the one thing this cannot pick up — that is what ``restart`` is for.
"""
import asyncio
import logging

from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.pins.runtime import drop_live_derived_pins

logger = logging.getLogger(__name__)


async def run_reload_harness(ctx: ToolContext) -> ToolResult:
    # cycle: harness_loader -> harness.app.core -> contrib.tools.registry -> here
    from hypergolic.cli.harness_loader import HarnessLoadError, reload_live_harness

    try:
        app = await asyncio.to_thread(reload_live_harness)
    except HarnessLoadError as exc:
        return ToolResult.text(
            f"Reload aborted; the previous configuration is still live.\n{exc}",
            is_error=True,
        )
    rebound = drop_live_derived_pins()
    logger.info(
        "Harness reloaded in place: %d projects, %d tools, %d skills, %d roles; "
        "%d override-pinned session(s) rebind on their next turn",
        len(app.projects), len(app.tools), len(app.skills), len(app.roles), len(rebound),
    )
    return ToolResult.text(
        "Harness reloaded from ~/.hypergolic without a restart: "
        f"{len(app.projects)} projects, {len(app.tools)} tools, "
        f"{len(app.skills)} skills, {len(app.roles)} roles. Turns already "
        "running finish on the old configuration; every session's next turn "
        "uses the new one. Edits to the hypergolic package itself are not "
        "picked up this way — those still need `restart`."
    )


reload_harness_tool = Tool(
    id="reload_harness",
    tags=["reload", "apply-changes", "pick-up-edits", "hot-reload", "harness", "no-restart"],
    name="Reload Harness",
    description="Apply landed ~/.hypergolic changes in place: rebuild the App from disk without restarting the server or interrupting other sessions",
    run=run_reload_harness,
    approval=always("ALLOW"),
)
