# Instrumenting the Harness
Tool calls already get a `tool <id>` span; code inside a tool runs in the harness process, so standard OTel calls nest under it:
```python
from opentelemetry import trace
with trace.get_tracer(__name__).start_as_current_span("fetch index", attributes={"index.size": n}):
    ...
```

## Conventions
- Put `session.id` on any span tied to a session so `--session` and TraceQL find it
- Work that outlives its caller (turn from a WebSocket message, reap, loop tick) starts its own trace with `hypergolic.telemetry.tracing.root_span`, linked to the caller — otherwise its SQL lands as ownerless root traces
- Wrap session-scoped work in `hypergolic.telemetry.log_context.log_context(**{"session.id": id})` so log lines carry the ids
- Blocking calls go through `asyncio.to_thread`; sync work on the loop shows up as `event_loop.stall`
- Never call `logging.config.*` / `fileConfig` after `setup_logging` — it strips the file and OTel handlers

## Source
`/hypergolic/telemetry/`: `tracing.py` (providers, exporters, `root_span`), `startup.py` (launch order, backend container), `session_trace.py`, `db_calls.py` (SQL caller), `sandbox_metrics.py`, `status.py`. Query side: `/tools/traces/source`.

## Verify
After a restart: `traces --status`, then find the new span by name with `traces '{ name = "<span>" }' --since 15m`.
