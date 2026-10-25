"""The per-project sandbox command tool, compiled from a ProjectSandbox model.

The model is compiled to a Compose file under ``~/.hypergolic_internals/sandboxes``
(a deterministic, regenerable asset kept out of the version-controlled harness
dir). ``Project.configure_sandbox`` writes it eagerly at harness-load time so the
file is present before any command runs (recovery after a restart re-reads it);
each ``cmd`` invocation rewrites it too (idempotently) so a changed model is
picked up. With more than one container the tool exposes a required, typed
``container`` enum; with one it is omitted.
"""

import asyncio
from enum import Enum
from pathlib import Path

import yaml

from hypergolic.config.settings import INTERNALS_DIR
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.sandbox.compose import EMPTY_BUILD_CONTEXT, compile_compose, render_squid_conf
from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID, WORKSPACE_MOUNT
from hypergolic.sandbox.model.sandbox import ProjectSandbox
from hypergolic.sandbox.tool.exec import run_in_sandbox
from hypergolic.sandbox.tool.heredoc import prepare_edit_heredocs

GENERATED_SANDBOX_DIR = INTERNALS_DIR / "sandboxes"


def compose_path(sandbox: ProjectSandbox) -> Path:
    """The path the sandbox's compiled compose file is (or will be) written to."""
    return GENERATED_SANDBOX_DIR / f"{sandbox.id}.compose.yaml"


def write_compose(sandbox: ProjectSandbox) -> str:
    """Compile a ProjectSandbox to disk (compose + optional squid.conf).

    Idempotent; safe to call on every use. ``start_sandbox`` re-reads the file
    at ``up`` time, so the only requirement is that it exists before then.
    """
    GENERATED_SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    # Build context for image=-derived workspace builds (kept empty).
    (GENERATED_SANDBOX_DIR / EMPTY_BUILD_CONTEXT).mkdir(exist_ok=True)
    path = compose_path(sandbox)
    path.write_text(yaml.safe_dump(compile_compose(sandbox), sort_keys=False))

    squid_conf = render_squid_conf(sandbox.egress)
    squid_path = GENERATED_SANDBOX_DIR / sandbox.squid_conf_filename()
    if squid_conf is not None:
        squid_path.write_text(squid_conf)
    elif squid_path.exists():
        squid_path.unlink()

    return str(path)


def make_project_sandbox_tool(sandbox: ProjectSandbox) -> Tool:
    """Build the per-project ``cmd`` tool for a configured ProjectSandbox.

    With more than one container the input schema gains a required, typed
    ``container`` enum (the declared container ids). With a single container the
    field is omitted entirely and exec targets that container implicitly.
    """
    config_path = str(compose_path(sandbox))
    container_ids = sandbox.container_ids
    is_multi = len(container_ids) > 1
    single_container = container_ids[0]
    # Containers that opted out of the /app workspace mount have no working dir
    # to cd into; don't inject -w /app for them (it would fail with "no such
    # file or directory").
    no_workdir = {c.id for c in sandbox.containers if c.skip_workspace_mount}

    if len(container_ids) > 1:
        ContainerEnum = Enum(  # type: ignore[misc]
            "ContainerEnum", {cid: cid for cid in container_ids}, type=str
        )

        class ProjectSandboxInput(InputSchema):
            container: ContainerEnum  # type: ignore[valid-type]
            command: str

        description = "Choose the container."
    else:

        class ProjectSandboxInput(InputSchema):  # type: ignore[no-redef]
            command: str

        description = ""

    async def run(inp: ProjectSandboxInput, ctx: ToolContext) -> ToolResult:
        if is_multi:
            chosen = getattr(inp, "container")  # required field; always present
            container = chosen.value if isinstance(chosen, Enum) else chosen
        else:
            container = single_container
        workdir = None if container in no_workdir else WORKSPACE_MOUNT
        # Idempotent + cheap; always materialize so a changed model is picked up.
        await asyncio.to_thread(write_compose, sandbox)
        # The transcript keeps the command as written; the exec runs the
        # repaired one, and the agent hears what changed in the result.
        command, notes = prepare_edit_heredocs(inp.command)
        result = await run_in_sandbox(
            ctx,
            config_path,
            command,
            container=container,
            workdir=workdir,
            timeout=sandbox.command_timeout,
        )
        if notes:
            result = result.append_text("[cmd] " + "; ".join(notes))
        return result

    # No qualifier, so the DBSandbox row is keyed on tool_id=SANDBOX_TOOL_ID.
    # The session context block scopes to that key. One configured
    # ProjectSandbox per project is the invariant.
    return Tool(
        id=SANDBOX_TOOL_ID,
        name="Sandbox Command",
        description=description,
        input_schema=ProjectSandboxInput,
        run=run,
        approval=always("ALLOW"),
    )
