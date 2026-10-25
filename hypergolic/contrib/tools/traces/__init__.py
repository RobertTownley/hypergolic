import asyncio
import json
import urllib.error

from hypergolic.commands.argv import positional
from hypergolic.config.settings import settings
from hypergolic.contrib.tools.traces.grafana import (
    fetch_trace,
    query_logs,
    query_metric,
    search,
)
from hypergolic.contrib.tools.traces.render import (
    logs_table,
    metric_table,
    search_table,
    trace_table,
)
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import CommandExample, CommandResult, InputSchema
from hypergolic.harness.primitives.tool import HOST, Tool, ToolContext
from hypergolic.telemetry.session_trace import session_trace_id_hex
from hypergolic.telemetry.status import telemetry_status


class TracesInput(InputSchema):
    query: str = "{}"
    trace: str = ""
    session: str = ""
    logs: str = ""
    metric: str = ""
    status: bool = False
    since: str = "1h"
    limit: int = 20


def _session_report(inp: TracesInput) -> str:
    start_id = session_trace_id_hex(inp.session)
    turns = search(
        f'{{ name = "turn" && span.session.id = "{inp.session}" }}', inp.since, inp.limit
    )
    return (
        f"session.start trace {start_id}:\n"
        f"{trace_table(fetch_trace(start_id), inp.limit)}\n\n"
        f"turns (last {inp.since}):\n{search_table(turns)}"
    )


def _run_sync(inp: TracesInput) -> str:
    if inp.status:
        return json.dumps(telemetry_status(), indent=2)
    if inp.logs:
        return logs_table(query_logs(inp.logs, inp.since, inp.limit))
    if inp.metric:
        return metric_table(query_metric(inp.metric))
    if inp.session:
        return _session_report(inp)
    if inp.trace:
        return trace_table(fetch_trace(inp.trace), inp.limit)
    return search_table(search(inp.query, inp.since, inp.limit))


async def run_traces(inp: TracesInput, _ctx: ToolContext) -> CommandResult:
    try:
        stdout = await asyncio.to_thread(_run_sync, inp)
    except (urllib.error.URLError, KeyError, ValueError) as e:
        return CommandResult.fail(f"{type(e).__name__}: {e}")
    return CommandResult(stdout=f"{stdout}\nGrafana: {settings.HYPERGOLIC_GRAFANA_URL}/explore")


traces_tool = Tool(
    id="traces",
    tags=["performance", "slow", "latency", "tracing", "opentelemetry", "tempo", "loki",
        "prometheus", "logs", "metrics", "profiling"],
    name="Traces",
    description="Query Hypergolic's own telemetry — traces (Tempo/TraceQL), logs (Loki/LogQL), metrics (Prometheus/PromQL) — to find where a session spends its time.",
    usage=(
        "traces [<traceql...>] | --trace <id> | --session <id> | --logs <logql> "
        "| --metric <promql> | --status  [--since 1h] [--limit 20]"
    ),
    guidance=(
        "Positional args are a TraceQL search; `--trace` lists one trace's slowest spans; "
        "`--session` shows a session's startup trace and turns; `--logs` takes LogQL, "
        "`--metric` PromQL; `--status` reports whether each signal leaves the process. "
        "`--since` takes m/h/d. Span names, fields, and recipes: "
        "`activate_skill harness-performance-investigating`."
    ),
    input_schema=TracesInput,
    examples=[
        CommandExample(
            command="traces --session <id> --since 1d",
            note="Startup trace of one session, then its turns with duration.",
        ),
        CommandExample(
            command="traces --status",
            note="Is each signal leaving the process? Check before blaming the query.",
        ),
        CommandExample(command="traces '{ name =~ \"tool.*\" && duration > 10s }'"),
        CommandExample(command="traces --trace <trace_id> --limit 30"),
        CommandExample(
            command="traces --logs '{service_name=\"hypergolic\"} | session_id=\"<id>\"' --since 2h",
            note="Log lines from one session, newest first.",
        ),
        CommandExample(
            command="traces --metric 'topk(10, sum by (code_function) (rate(db_client_queries_total[5m])))'",
            note="Which code sends the most SQL right now.",
        ),
    ],
    domain=HOST,
    approval=always("ALLOW"),
    argv=positional(
        joined="query", values={"trace", "session", "logs", "metric", "since", "limit"},
        bools={"status"},
    ),
    run=run_traces,
)
