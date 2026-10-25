# Harness Performance
Hypergolic sends its own OpenTelemetry traces, logs, and metrics to a local Grafana (`grafana/otel-lgtm`: Tempo traces, Loki logs, Prometheus metrics). `traces` queries all three; every result ends with the Grafana link for the user.

Recorded: launch, session start, each turn, model call, tool call, sandbox command, broker call, HTTP route, and SQL query; every log line; per-sandbox CPU/memory/pids. Session-scoped spans and logs carry `session.id`.

Analytics events (`hypergolic.telemetry.events.emit`; UI ones arrive as `ui.*`) are log lines with `event_name` and `event_*` fields, counted by `hypergolic_events_total{event_name}`. Example: `traces --logs '{service_name="hypergolic"} | event_name=~"approval.*"'`.

Run `traces --status` first when anything looks missing: it reports, from inside the process, whether each signal is leaving it.
