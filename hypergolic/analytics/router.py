from fastapi import APIRouter, Query

from hypergolic.analytics.performance import query_performance
from hypergolic.analytics.queries import query_summary, query_timeseries, query_tool_usage
from hypergolic.analytics.schemas import (
    AnalyticsSummary,
    PerformanceReport,
    TimeseriesPoint,
    ToolCount,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
    project_id: str | None = Query(None),
    days: int | None = Query(None),
):
    return query_summary(project_id, days)


@router.get("/timeseries", response_model=list[TimeseriesPoint])
def get_timeseries(
    project_id: str | None = Query(None),
    days: int | None = Query(None),
    granularity: str = Query("day"),
):
    return query_timeseries(project_id, days, granularity)


@router.get("/tools", response_model=list[ToolCount])
def get_tool_usage(
    project_id: str | None = Query(None),
    days: int | None = Query(None),
):
    return query_tool_usage(project_id, days)


@router.get("/performance", response_model=PerformanceReport)
def get_performance(minutes: int = Query(60, ge=5, le=10080)):
    return query_performance(minutes)
