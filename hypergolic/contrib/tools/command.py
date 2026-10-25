import asyncio
import subprocess
from typing import Optional

from pydantic import Field

from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.tools.approval_view import (
    ApprovalView,
    BadgeBlock,
    CodeBlock,
    ForEachBlock,
)
from hypergolic.tools.subprocess_util import format_exec_output, run_subprocess
from hypergolic.commands.argv import host_argv


class CommandInput(InputSchema):
    commands: list[str] = Field(min_length=1)
    working_directory: Optional[str] = None
    timeout: int = Field(default=60, gt=0)


async def _run_one(command: str, cwd: str, timeout: int) -> tuple[str, bool]:
    try:
        result = await run_subprocess(
            command,
            shell=True,
            timeout=timeout,
            cwd=cwd,
        )
        text = format_exec_output(result.stdout, result.stderr, result.returncode)
        return text, result.returncode == 0
    except subprocess.TimeoutExpired:
        return (
            f"Command timed out after {timeout} seconds.",
            False,
        )
    except FileNotFoundError:
        return f"Working directory not found: {cwd}", False
    except Exception as e:
        return f"Error executing command: {str(e)}", False


async def run_command(inp: CommandInput, ctx: ToolContext) -> ToolResult:
    cwd = inp.working_directory or str(ctx.session.working_directory())

    results = await asyncio.gather(*(_run_one(c, cwd, inp.timeout) for c in inp.commands))

    if len(results) == 1:
        text, ok = results[0]
        return ToolResult.text(text, is_error=not ok)

    all_ok = all(ok for _, ok in results)
    text = "\n\n".join(
        f"$ {command}\n{output}"
        for command, (output, _) in zip(inp.commands, results)
    )
    return ToolResult.text(text, is_error=not all_ok)


command_tool = Tool(
    id="host_cmd",
    tags=["host", "unsandboxed", "outside-sandbox", "escape-hatch"],
    name="Host Command",
    description="Unsandboxed host, needs user approval",
    input_schema=CommandInput,
    argv=host_argv,
    usage="host_cmd [--cwd DIR] [--timeout SECONDS] <command...>",
    run=run_command,
    approval=always("REQUIRE_APPROVAL"),
    requires_worktree=True,
    approval_view=ApprovalView(blocks=[
        ForEachBlock(
            field="commands",
            template=[CodeBlock(field=".", language="bash", max_height=104)],
            separator="gap",
        ),
        BadgeBlock(field="working_directory", label="CWD", tone="info"),
    ]),
)

# HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE variant: with no sandbox, the host shell
# *is* `cmd` — same familiar id, and no description (the standard host-approval
# line would misdirect the model).
dangerous_command_tool = command_tool.model_copy(
    update={"id": "cmd", "description": ""}
)
