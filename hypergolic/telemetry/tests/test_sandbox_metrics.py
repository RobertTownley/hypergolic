import pytest

from hypergolic.telemetry.sandbox_metrics import parse_stats

LABELS = {
    "hypergolic.session": "S1",
    "com.docker.compose.project": "hgcmdabc",
    "com.docker.compose.service": "dev",
}


def test_parse_stats_reads_cumulative_cpu_and_working_set() -> None:
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 12_500_000_000},
            "throttling_data": {"throttled_time": 2_000_000_000},
        },
        "memory_stats": {"usage": 300, "limit": 1000, "stats": {"inactive_file": 100}},
        "pids_stats": {"current": 42},
    }
    sample = parse_stats(LABELS, "idle", stats)
    assert sample.cpu_seconds == pytest.approx(12.5)
    assert sample.throttled_seconds == pytest.approx(2.0)
    assert sample.memory_bytes == 200
    assert sample.memory_limit_bytes == 1000
    assert sample.pids == 42
    assert sample.attributes() == {
        "session.id": "S1",
        "session.state": "idle",
        "sandbox.compose_project": "hgcmdabc",
        "sandbox.container": "dev",
    }


def test_parse_stats_tolerates_missing_sections() -> None:
    sample = parse_stats(LABELS, "active", {"cpu_stats": {"cpu_usage": {"total_usage": 0}}})
    assert (sample.throttled_seconds, sample.memory_bytes, sample.pids) == (0, 0, 0)
