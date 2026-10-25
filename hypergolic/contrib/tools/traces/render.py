from __future__ import annotations

from datetime import datetime
from typing import Any

from hypergolic.contrib.tools.traces.grafana import attr_map

_SHOWN_ATTRS = ("session.id", "tool.id", "gen_ai.usage.output_tokens", "code.function",
    "db.statement")
_LOG_LABELS = ("detected_level", "severity_text", "session_id", "trace_id", "code_function")


def _ms(nanos: int | str) -> float:
    return int(nanos) / 1e6


def _attrs(span: dict[str, Any]) -> str:
    attrs = attr_map(span.get("attributes", []))
    shown = {k: str(attrs[k])[:80] for k in _SHOWN_ATTRS if k in attrs}
    return " ".join(f"{k}={v}" for k, v in shown.items())


def _matched(span: dict[str, Any]) -> str:
    name = span.get("name") or f"span {span.get('spanID', '?')}"
    duration = span.get("durationNanos")
    timing = f"{_ms(duration):.0f}ms" if duration is not None else "?ms"
    return f"{name} {timing} {_attrs(span)}".strip()


def search_table(traces: list[dict[str, Any]]) -> str:
    lines = ["trace_id\troot\tduration_ms\tmatched_spans"]
    for t in traces:
        spans = [s for ss in t.get("spanSets", []) for s in ss.get("spans", [])]
        matched = ", ".join(_matched(s) for s in spans)
        lines.append(f"{t['traceID']}\t{t.get('rootTraceName', '?')}\t"
            f"{t.get('durationMs', '?')}\t{matched}")
    return "\n".join(lines) if traces else lines[0] + "\n(0 traces)"


def trace_table(spans: list[dict[str, Any]], limit: int) -> str:
    if not spans:
        return "(trace not found)"
    t0 = min(int(s["startTimeUnixNano"]) for s in spans)
    rows = sorted(spans, key=lambda s: int(s["endTimeUnixNano"]) - int(s["startTimeUnixNano"]),
        reverse=True)[:limit]
    rows.sort(key=lambda s: int(s["startTimeUnixNano"]))
    lines = ["offset_ms\tduration_ms\tspan\tattributes"]
    for s in rows:
        start, end = int(s["startTimeUnixNano"]), int(s["endTimeUnixNano"])
        lines.append(f"{_ms(start - t0):.0f}\t{_ms(end - start):.0f}\t{s['name']}\t{_attrs(s)}")
    return "\n".join(lines)


def logs_table(rows: list[tuple[int, str, dict[str, str]]]) -> str:
    if not rows:
        return "(0 log lines)"
    lines = []
    for ns, line, labels in rows:
        at = datetime.fromtimestamp(ns / 1e9).strftime("%H:%M:%S.%f")[:-3]
        shown = " ".join(f"{k}={labels[k]}" for k in _LOG_LABELS if labels.get(k))
        lines.append(f"{at}\t{shown}\t{line[:300]}")
    return "\n".join(lines)


def metric_table(result: list[dict[str, Any]]) -> str:
    if not result:
        return "(no series)"
    lines = ["value\tlabels"]
    rows = sorted(result, key=lambda r: float(r["value"][1]), reverse=True)
    for r in rows:
        labels = ",".join(f"{k}={v}" for k, v in r["metric"].items())
        lines.append(f"{float(r['value'][1]):.4g}\t{labels}")
    return "\n".join(lines)
