from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from hypergolic.analytics.schemas import AnalyticsSummary, TimeseriesPoint, ToolCount
from hypergolic.db.engine import get_db

PRICING = {
    "Low": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.10},
    "Medium": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "High": {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "Extra High": {
        "input": 10.0,
        "output": 50.0,
        "cache_write": 12.5,
        "cache_read": 1.0,
    },
}


# Analytics runs raw SQL for JSON aggregation (->> operators,
# json_array_elements, to_char).
_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _usage_sum(key: str) -> str:
    """SUM of a numeric field inside the ``messages.usage`` JSON column."""
    # ->> yields text; cast so SUM is numeric rather than a string concat error.
    return f"COALESCE(SUM((m.usage ->> '{key}')::bigint), 0)"


def _period_expr(granularity: str) -> str:
    """Truncate ``sessions.created_at`` to the requested bucket."""
    if granularity == "week":
        fmt = 'IYYY"-W"IW'
    elif granularity == "month":
        fmt = "YYYY-MM"
    else:
        fmt = "YYYY-MM-DD"
    return f"to_char(s.created_at, '{fmt}')"


def date_filter(days: int | None) -> datetime | None:
    if days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def compute_cost(
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
    model_tier: str,
) -> float:
    rates = PRICING.get(model_tier, PRICING["High"])
    return (
        (input_tokens / 1_000_000) * rates["input"]
        + (output_tokens / 1_000_000) * rates["output"]
        + (cache_write_tokens / 1_000_000) * rates["cache_write"]
        + (cache_read_tokens / 1_000_000) * rates["cache_read"]
    )


def build_where_clause(
    project_id: str | None,
    cutoff: datetime | None,
    *,
    extra: list[str] | None = None,
) -> tuple[str, dict]:
    """Build a shared WHERE clause and params dict used by all analytics endpoints."""
    where_clauses: list[str] = list(extra) if extra else []
    params: dict = {}
    if project_id:
        where_clauses.append("s.project_id = :project_id")
        params["project_id"] = project_id
    if cutoff:
        where_clauses.append("s.created_at >= :cutoff")
        params["cutoff"] = cutoff.isoformat()
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    return where_sql, params


def _as_ints(*values: Any) -> tuple[int, ...]:
    """Postgres SUM(bigint) yields Decimal, which breaks Decimal * float in compute_cost."""
    return tuple(int(value) for value in values)


def _aggregate_summary_rows(rows: Sequence[Sequence[Any]]) -> AnalyticsSummary:
    """Aggregate per-tier rows into a single AnalyticsSummary."""
    total_sessions = 0
    total_messages = 0
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_cw = 0
    total_cr = 0

    for row in rows:
        tier, sess_count, msg_count, inp, out, cw, cr = row
        inp, out, cw, cr = _as_ints(inp, out, cw, cr)
        total_sessions += sess_count
        total_messages += msg_count
        total_input += inp
        total_output += out
        total_cw += cw
        total_cr += cr
        total_cost += compute_cost(inp, out, cw, cr, tier)

    return AnalyticsSummary(
        total_sessions=total_sessions,
        total_messages=total_messages,
        total_cost=round(total_cost, 4),
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_write_tokens=total_cw,
        total_cache_read_tokens=total_cr,
    )


def _aggregate_timeseries_rows(rows: Sequence[Sequence[Any]]) -> list[TimeseriesPoint]:
    """Aggregate per-tier/period rows into TimeseriesPoint list."""
    period_data: dict[str, TimeseriesPoint] = {}
    for row in rows:
        period, tier, sess_count, msg_count, inp, out, cw, cr = row
        inp, out, cw, cr = _as_ints(inp, out, cw, cr)
        if period not in period_data:
            period_data[period] = TimeseriesPoint(
                period=period,
                sessions=0,
                messages=0,
                cost=0.0,
                input_tokens=0,
                output_tokens=0,
                cache_write_tokens=0,
                cache_read_tokens=0,
            )
        pt = period_data[period]
        pt.sessions += sess_count
        pt.messages += msg_count
        pt.input_tokens += inp
        pt.output_tokens += out
        pt.cache_write_tokens += cw
        pt.cache_read_tokens += cr
        pt.cost += compute_cost(inp, out, cw, cr, tier)

    for pt in period_data.values():
        pt.cost = round(pt.cost, 4)

    return list(period_data.values())


def query_summary(
    project_id: str | None,
    days: int | None,
) -> AnalyticsSummary:
    cutoff = date_filter(days)
    where_sql, params = build_where_clause(project_id, cutoff)

    inp, out, cw, cr = (_usage_sum(k) for k in _USAGE_KEYS)
    sql = f"""
        SELECT
            s.model_tier,
            COUNT(DISTINCT s.id) as session_count,
            COUNT(m.id) as message_count,
            {inp} as input_tokens,
            {out} as output_tokens,
            {cw} as cache_write_tokens,
            {cr} as cache_read_tokens
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id AND m.usage IS NOT NULL
        {where_sql}
        GROUP BY s.model_tier
    """

    with get_db() as db:
        rows = db.execute(text(sql), params).fetchall()

    return _aggregate_summary_rows(rows)


def query_timeseries(
    project_id: str | None,
    days: int | None,
    granularity: str,
) -> list[TimeseriesPoint]:
    cutoff = date_filter(days)

    period_expr = _period_expr(granularity)
    where_sql, params = build_where_clause(project_id, cutoff)
    inp, out, cw, cr = (_usage_sum(k) for k in _USAGE_KEYS)

    sql = f"""
        SELECT
            {period_expr} as period,
            s.model_tier,
            COUNT(DISTINCT s.id) as session_count,
            COUNT(m.id) as message_count,
            {inp} as input_tokens,
            {out} as output_tokens,
            {cw} as cache_write_tokens,
            {cr} as cache_read_tokens
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id AND m.usage IS NOT NULL
        {where_sql}
        GROUP BY period, s.model_tier
        ORDER BY period
    """

    with get_db() as db:
        rows = db.execute(text(sql), params).fetchall()

    return _aggregate_timeseries_rows(rows)


def query_tool_usage(
    project_id: str | None,
    days: int | None,
) -> list[ToolCount]:
    cutoff = date_filter(days)
    unnest = "CROSS JOIN LATERAL json_array_elements(m.content) AS block(value)"
    name_expr = "block.value ->> 'name'"
    type_expr = "block.value ->> 'type'"

    where_sql, params = build_where_clause(
        project_id,
        cutoff,
        extra=["m.role = 'assistant'", f"{type_expr} = 'tool_use'"],
    )

    sql = f"""
        SELECT
            {name_expr} as tool_name,
            COUNT(*) as call_count
        FROM messages m
        JOIN sessions s ON s.id = m.session_id
        {unnest}
        {where_sql}
        GROUP BY tool_name
        ORDER BY call_count DESC
    """

    with get_db() as db:
        rows = db.execute(text(sql), params).fetchall()

    return [ToolCount(tool_name=name, count=count) for name, count in rows]
