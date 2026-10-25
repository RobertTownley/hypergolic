# Investigating Harness Performance

## Path
1. `traces --status` — every signal `failures: 0` with a recent `seconds_since_last`; else see Broken Pipeline
2. `traces --session <id> --since 1d` — the `session.start` trace, then turns by duration
3. `traces --trace <trace_id> --limit 40` on the slowest turn — widest child spans first
4. `--logs` / `--metric` over the same window for what the spans don't say

## Reading Spans
- `turn` is one agent turn; it links to `session.start` (its trace id derives from the session id). A turn still running shows `?` as its root in search
- `llm.stream` — one model call. Event `first_content_block` marks time to first token; `gen_ai.usage.*` holds token and cache counts. Usually most of a turn
- `tool <id>` — one tool call, own tools included (`tool.id`)
- `sandbox.exec` — one `docker compose exec`; `exec.first_output_ms` includes ~100 ms compose startup on every command. Child `sandbox.recover` = container restart
- `broker <command>` — a sandbox calling a host command, under its `sandbox.exec`. Child `broker.approval` is time waiting on the human, not slowness
- `sandbox.start` — `compose up` inside `workspace.provision`
- `event_loop.stall` — sync work blocked the loop and froze every session at once; `stall.culprit` names the frame, `stall.ms` the length
- SQL spans — `code.function` is the hypergolic function that sent the query. Root SQL traces are background work without a span

## Queries
- Slow tools: `traces '{ name =~ "tool.*" && duration > 10s }'`
- Stalls: `traces '{ name = "event_loop.stall" }' --since 6h`
- One session's logs: `traces --logs '{service_name="hypergolic"} | session_id="<id>"'` (Loki fields use `_` for `.`)
- Who sends SQL: `traces --metric 'topk(10, sum by (code_function) (rate(db_client_queries_total[5m])))'`
- SQL time: `db_client_query_duration_seconds_sum` / `_count` by `code_function`, `db_operation`; `db_root="true"` = ran outside any trace
- Sandbox pressure: `rate(sandbox_cpu_time_seconds_total[5m])` (cores), `sandbox_cpu_throttled_seconds_total`, `sandbox_memory_usage_bytes` vs `sandbox_memory_limit_bytes`, `sandbox_pids` by `session_id`, `session_state`, `sandbox_container`; per-command cost: `sandbox_exec_duration_seconds_*`, `sandbox_exec_cpu_seconds_total` by `exec_program`; harness: `harness_cpu_time_seconds_total`, `harness_memory_rss_bytes`, `event_loop_lag_seconds_bucket`

## Broken Pipeline
`--status` (same as `GET /api/telemetry/status`):
- `exports.<signal>.failures` / `last_error` — backend unreachable or rejecting
- `queues.<signal>` — high `queued` or `worker_alive: false` = exporter thread stuck
- `providers.*.is_ours: false` — something replaced the global OTel provider
- `log_handler.on_root: false` — something reconfigured logging after startup (`logging.config`, alembic `fileConfig`); `seen` > `emitted` = a filter drops records
