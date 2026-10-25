from __future__ import annotations

from enum import Enum

from hypergolic.readiness.probes import (
    ProbeResult,
    render_scorecard,
    run_smoke_probes,
    run_static_probes,
)
from hypergolic.harness.app.state import get_app
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.sandbox.manager.types import SandboxError, SandboxUnavailableError
from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID
from hypergolic.commands.argv import positional

_SANDBOX_KEY = SANDBOX_TOOL_ID
_EXEC_TIMEOUT = 60


class ProbeTier(str, Enum):
    static = "static"
    smoke = "smoke"
    all = "all"


class ReadinessInput(InputSchema):
    tier: ProbeTier = ProbeTier.all


def _text(result_lines: str, ok: bool) -> ToolResult:
    return ToolResult.text(result_lines, is_error=not ok)


async def _smoke(ctx: ToolContext, project) -> list[ProbeResult]:
    from hypergolic.sandbox.manager import sandbox_rows
    from hypergolic.sandbox.manager.exec import exec_in_sandbox
    from hypergolic.sandbox.manager.start import needs_start, start_sandbox
    from hypergolic.sandbox.tool.project_tool import compose_path, write_compose

    sandbox = project.resolved_sandbox
    if sandbox is None:
        return [
            ProbeResult(
                "sandbox",
                "smoke",
                None,
                "project opted out of sandbox (configure_sandbox(None)); smoke tier skipped",
            )
        ]

    write_compose(sandbox)
    config = str(compose_path(sandbox))
    session_id = ctx.session.id
    project_root = str(ctx.session.working_directory())

    row = await sandbox_rows.get(session_id, _SANDBOX_KEY)
    if needs_start(row, config):
        try:
            await start_sandbox(
                session_id=session_id,
                tool_id=_SANDBOX_KEY,
                config_path=config,
                project_root=project_root,
                sandbox_id=_SANDBOX_KEY,
            )
        except (SandboxUnavailableError, SandboxError) as e:
            return [
                ProbeResult(
                    "sandbox-up",
                    "smoke",
                    False,
                    str(e),
                    "start Docker / fix the ProjectSandbox config, then rerun",
                )
            ]
    results = [ProbeResult("sandbox-up", "smoke", True, "compose stack running")]
    results.extend(await _repo_probes(ctx, project))

    async def exec_fn(command: str, container: str) -> tuple[int, str]:
        r = await exec_in_sandbox(
            session_id=session_id,
            tool_id=_SANDBOX_KEY,
            command=command,
            timeout=_EXEC_TIMEOUT,
            sandbox_id=_SANDBOX_KEY,
            project_root=project_root,
            container=container,
        )
        out = "\n".join(p for p in (r.stdout, r.stderr) if p).strip()
        return r.returncode, out

    results.extend(await run_smoke_probes(project, sandbox, exec_fn))
    return results


async def _repo_probes(ctx: ToolContext, project) -> list[ProbeResult]:
    from hypergolic.sandbox.manager.repo_provision import provision_sandbox
    from hypergolic.sandbox.manager.repo_report import pop_report_warnings

    steps = await provision_sandbox(ctx.session, project)
    pop_report_warnings(ctx.session.id)
    return [
        ProbeResult(f"repo-{s.repo}", "smoke", s.ok, s.detail or s.action, s.fix)
        for s in steps
    ]


async def _run(inp: ReadinessInput, ctx: ToolContext) -> ToolResult:
    project = (
        get_app().find_project(ctx.session.project_id) if ctx.session.project_id else None
    )
    if project is None:
        return _text("No project registered for this session.", ok=False)

    results: list[ProbeResult] = []
    if inp.tier in (ProbeTier.static, ProbeTier.all):
        results.extend(run_static_probes(project))
    if inp.tier in (ProbeTier.smoke, ProbeTier.all):
        results.extend(await _smoke(ctx, project))

    return _text(render_scorecard(results), ok=all(r.passed is not False for r in results))


readiness_probes_tool = Tool(
    id="run_readiness_probes",
    tags=["readiness", "probe", "smoke-test", "scorecard", "diagnose", "agent-readiness"],
    name="Run Readiness Probes",
    description=(
        "Probe agent-readiness (static = config checks, smoke = sandbox "
        "execs). Scorecard with a fix per failure"
    ),
    input_schema=ReadinessInput,
    argv=positional("tier"),
    usage="run_readiness_probes [<tier>]",
    timeout=300,
    run=_run,
)
