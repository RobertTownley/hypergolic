from __future__ import annotations

import time
from typing import Any

from hypergolic.telemetry.grafana import datasource_get as _get
from hypergolic.telemetry.grafana import prom_query

_UNITS = {"m": 60, "h": 3600, "d": 86400}
#: Without an explicit select, Tempo returns matched spans with ids and
#: timings only, no name.
_SELECT = " | select(name, span.session.id, span.tool.id, span.code.function)"


def since_seconds(since: str) -> int:
    return int(since[:-1]) * _UNITS[since[-1]]


def with_select(traceql: str) -> str:
    return traceql if "select(" in traceql else traceql + _SELECT


def search(traceql: str, since: str, limit: int) -> list[dict[str, Any]]:
    end = int(time.time())
    params = {"q": with_select(traceql), "start": end - since_seconds(since), "end": end,
        "limit": limit, "spss": 10}
    return _get("tempo", "/api/search", params).get("traces", [])


def fetch_trace(trace_id: str) -> list[dict[str, Any]]:
    payload = _get("tempo", f"/api/v2/traces/{trace_id}")
    batches = payload.get("trace", payload).get("resourceSpans", [])
    return [span for b in batches for s in b.get("scopeSpans", []) for span in s.get("spans", [])]


def query_logs(logql: str, since: str, limit: int) -> list[tuple[int, str, dict[str, str]]]:
    """Newest first: (unix ns, line, stream labels + structured metadata)."""
    end = time.time_ns()
    params = {"query": logql, "start": end - since_seconds(since) * 10**9, "end": end,
        "limit": limit, "direction": "backward"}
    result = _get("loki", "/loki/api/v1/query_range", params)["data"]["result"]
    rows = []
    for stream in result:
        labels = stream.get("stream", {})
        for value in stream.get("values", []):
            meta = value[2] if len(value) > 2 else {}
            rows.append((int(value[0]), value[1], {**labels, **meta}))
    rows.sort(key=lambda r: r[0], reverse=True)
    return rows[:limit]


def query_metric(promql: str) -> list[dict[str, Any]]:
    return prom_query(promql)


def attr_map(attributes: list[dict[str, Any]]) -> dict[str, Any]:
    return {a["key"]: next(iter(a["value"].values()), None) for a in attributes}
