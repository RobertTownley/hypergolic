from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from hypergolic.analytics.schemas import (
    PerformanceCards,
    PerformanceReport,
    ProgramCost,
    SeriesPoint,
    SessionCost,
)
from hypergolic.db.engine import get_db
from hypergolic.db.models import DBSession
from hypergolic.telemetry.grafana import prom_query, prom_range
from hypergolic.telemetry.sandbox_metrics import session_state

_CPU = "sandbox_cpu_time_seconds_total"
_POINTS = 60
_LIVE = "count by (session_id) (sandbox_pids)"


def _scalar(promql: str) -> float | None:
    result = prom_query(promql)
    value = float(result[0]["value"][1]) if result else math.nan
    return value if math.isfinite(value) else None


def _by(label: str, promql: str) -> dict[str, float]:
    return {r["metric"].get(label, ""): float(r["value"][1]) for r in prom_query(promql)}


def _cards(window: str) -> PerformanceCards:
    states = [state for _, state in _session_info(list(_by("session_id", _LIVE))).values()]
    return PerformanceCards(
        sandboxes=len(states),
        idle_sandboxes=sum(state != "active" for state in states),
        sandbox_cores=_scalar(f"sum(rate({_CPU}[2m]))"),
        idle_cpu_share=_scalar(
            f'sum(rate({_CPU}{{session_state!="active"}}[{window}])) / sum(rate({_CPU}[{window}]))'
        ),
        sandbox_memory_bytes=_scalar("sum(sandbox_memory_usage_bytes)"),
        throttled_cores=_scalar(f"sum(rate(sandbox_cpu_throttled_seconds_total[{window}]))"),
        harness_cores=_scalar("sum(rate(harness_cpu_time_seconds_total[2m]))"),
        harness_rss_bytes=_scalar("sum(harness_memory_rss_bytes)"),
        loop_lag_p95_s=_scalar(
            f"histogram_quantile(0.95, sum by (le) (rate(event_loop_lag_seconds_bucket[{window}])))"
        ),
    )


def _series(promql: str, label: str, minutes: int) -> list[SeriesPoint]:
    end = time.time()
    step = max(15, minutes * 60 // _POINTS)
    points: dict[float, dict[str, float]] = {}
    for row in prom_range(promql, end - minutes * 60, end, step):
        key = row["metric"].get(label, "")
        for at, value in row["values"]:
            points.setdefault(float(at), {})[key] = round(float(value), 3)
    return [SeriesPoint(at=at, values=values) for at, values in sorted(points.items())]


def _session_info(session_ids: list[str]) -> dict[str, tuple[str | None, str]]:
    with get_db() as db:
        rows = db.execute(
            select(DBSession.id, DBSession.description, DBSession.status)
            .where(DBSession.id.in_(session_ids))
        ).all()
    return {sid: (description, session_state(status)) for sid, description, status in rows}


def _sessions(window: str) -> list[SessionCost]:
    cpu = _by("session_id", f"topk(10, sum by (session_id) (increase({_CPU}[{window}])))")
    memory = _by("session_id", "sum by (session_id) (sandbox_memory_usage_bytes)")
    info = _session_info(list(cpu))
    rows = [SessionCost(session_id=sid, description=info.get(sid, (None, "gone"))[0],
                        state=info.get(sid, (None, "gone"))[1],
                        cpu_seconds=seconds, memory_bytes=memory.get(sid))
            for sid, seconds in cpu.items()]
    return sorted(rows, key=lambda r: r.cpu_seconds, reverse=True)


def _programs(window: str) -> list[ProgramCost]:
    def by_program(metric: str) -> dict[str, float]:
        # These counters start at zero, so a series that first appears inside
        # the window counts as its full value. increase() would drop its first
        # sample, or the whole series when it has only one sample.
        old = f"(increase({metric}[{window}]) and {metric} offset {window})"
        return _by("exec_program", f"sum by (exec_program) ({old} or max_over_time({metric}[{window}]))")
    runs = by_program("sandbox_exec_duration_seconds_count")
    wall = by_program("sandbox_exec_duration_seconds_sum")
    cpu = by_program("sandbox_exec_cpu_seconds_total")
    rows = [ProgramCost(program=p, runs=round(n), wall_seconds=wall.get(p, 0), cpu_seconds=cpu.get(p))
            for p, n in runs.items() if n >= 0.5]
    return sorted(rows, key=lambda r: r.cpu_seconds or 0, reverse=True)[:12]


def _cpu_series(minutes: int) -> list[SeriesPoint]:
    rate = f"{max(2, minutes // _POINTS * 2)}m"
    return _series(f"sum by (sandbox_container) (rate({_CPU}[{rate}]))", "sandbox_container", minutes)


def _memory_series(minutes: int) -> list[SeriesPoint]:
    return _series("sum by (sandbox_container) (sandbox_memory_usage_bytes)", "sandbox_container", minutes)


def query_performance(minutes: int) -> PerformanceReport:
    window = f"{minutes}m"
    parts: dict[str, Callable[[], Any]] = {
        "cards": lambda: _cards(window),
        "cpu_by_container": lambda: _cpu_series(minutes),
        "memory_by_container": lambda: _memory_series(minutes),
        "sessions": lambda: _sessions(window),
        "programs": lambda: _programs(window),
    }
    try:
        return PerformanceReport(available=True, **{name: build() for name, build in parts.items()})
    except OSError as exc:
        return PerformanceReport(available=False, error=f"Telemetry backend unreachable: {exc}")
