from unittest.mock import patch

from hypergolic.analytics import performance


def _instant(promql: str) -> list[dict]:
    if "by (exec_program)" in promql:
        return [{"metric": {"exec_program": "pytest"}, "value": [0, "4"]}]
    if "by (session_id)" in promql:
        return [{"metric": {"session_id": "S1"}, "value": [0, "30"]}]
    if "histogram_quantile" in promql:
        return [{"metric": {}, "value": [0, "NaN"]}]
    return [{"metric": {}, "value": [0, "2"]}]


def _range(promql: str, start: float, end: float, step: int) -> list[dict]:
    return [{"metric": {"sandbox_container": "dev"}, "values": [[100, "0.5"], [115, "0.75"]]}]


def test_query_performance_assembles_report() -> None:
    with (
        patch.object(performance, "prom_query", _instant),
        patch.object(performance, "prom_range", _range),
        patch.object(performance, "_session_info", lambda ids: {"S1": ("fix bug", "idle")}),
    ):
        report = performance.query_performance(60)
    assert report.available
    assert report.cards is not None
    assert (report.cards.sandboxes, report.cards.idle_sandboxes) == (1, 1)
    assert report.cards.loop_lag_p95_s is None
    assert [p.values for p in report.cpu_by_container] == [{"dev": 0.5}, {"dev": 0.75}]
    [session] = report.sessions
    assert (session.description, session.state, session.cpu_seconds) == ("fix bug", "idle", 30)
    [program] = report.programs
    assert (program.program, program.runs) == ("pytest", 4)


def test_query_performance_reports_unreachable_backend() -> None:
    def fail(*_args: object) -> list[dict]:
        raise ConnectionRefusedError("refused")

    with patch.object(performance, "prom_query", fail):
        report = performance.query_performance(60)
    assert not report.available and "refused" in (report.error or "")
