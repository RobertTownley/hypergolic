import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from hypergolic.analytics.queries import (
    _aggregate_summary_rows,
    _aggregate_timeseries_rows,
    build_where_clause,
    compute_cost,
    date_filter,
)
from tests.conftest import make_message, make_project, make_session

USAGE = {"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 100}
COST = round(compute_cost(1000, 500, 200, 100, "High"), 4)
CUTOFF = datetime(2025, 1, 1, tzinfo=timezone.utc)
ALL_OF_PROJ_1 = {"project_id": "proj-1", "days": 9999}


def _seed(project_id: str = "proj-1") -> None:
    sid = make_session(project_id, model_tier="High")
    make_message(sid, "assistant", model="claude", usage=USAGE,
                 content=[{"type": "tool_use", "name": "cat", "id": "x", "input": {}}])


def test_date_filter():
    assert date_filter(None) is None
    cutoff = date_filter(7)
    assert cutoff is not None
    assert abs((cutoff - (datetime.now(timezone.utc) - timedelta(days=7))).total_seconds()) < 2


def test_compute_cost():
    assert compute_cost(1_000_000, 1_000_000, 1_000_000, 1_000_000, "High") == 5.0 + 25.0 + 6.25 + 0.50
    assert compute_cost(1000, 500, 200, 100, "Unknown") == compute_cost(1000, 500, 200, 100, "High")


@pytest.mark.parametrize("project_id, cutoff, extra, where_sql, params", [
    (None, None, None, "", {}),
    ("proj-1", None, None, "WHERE s.project_id = :project_id", {"project_id": "proj-1"}),
    (None, CUTOFF, ["m.role = 'assistant'"], "WHERE m.role = 'assistant' AND s.created_at >= :cutoff",
     {"cutoff": CUTOFF.isoformat()}),
])
def test_build_where_clause(project_id, cutoff, extra, where_sql, params):
    assert build_where_clause(project_id, cutoff, extra=extra) == (where_sql, params)


def test_aggregation_accepts_postgres_decimal_sums():
    sums = (Decimal(1000), Decimal(500), Decimal(200), Decimal(100))
    summary = _aggregate_summary_rows([("High", 1, 1, *sums)])
    assert (summary.total_input_tokens, summary.total_cache_read_tokens, summary.total_cost) == (1000, 100, COST)
    [point] = _aggregate_timeseries_rows([("2026-01-01", "High", 1, 1, *sums)])
    assert (point.input_tokens, point.cost) == (1000, COST)


@pytest.mark.db
def test_summary(api_client, seed_project):
    assert api_client.get("/api/analytics/summary").json()["total_sessions"] == 0
    make_project("proj-2", "Other", "/tmp/other")
    _seed("proj-1")
    _seed("proj-2")

    data = api_client.get("/api/analytics/summary", params=ALL_OF_PROJ_1).json()
    assert data == {
        "total_sessions": 1, "total_messages": 1, "total_cost": COST, "total_input_tokens": 1000,
        "total_output_tokens": 500, "total_cache_write_tokens": 200, "total_cache_read_tokens": 100,
    }


@pytest.mark.db
@pytest.mark.parametrize("granularity, period", [
    ("day", r"\d{4}-\d{2}-\d{2}"), ("week", r"\d{4}-W\d{2}"), ("month", r"\d{4}-\d{2}"),
])
def test_timeseries(api_client, seed_project, granularity, period):
    assert api_client.get("/api/analytics/timeseries").json() == []
    _seed()
    [point] = api_client.get("/api/analytics/timeseries", params={"granularity": granularity, **ALL_OF_PROJ_1}).json()
    assert re.fullmatch(period, point["period"])
    assert (point["sessions"], point["messages"]) == (1, 1)


@pytest.mark.db
def test_tool_usage(api_client, seed_project):
    assert api_client.get("/api/analytics/tools").json() == []
    _seed()
    for params in ({}, ALL_OF_PROJ_1):
        [row] = api_client.get("/api/analytics/tools", params=params).json()
        assert (row["tool_name"], row["count"]) == ("cat", 1)
