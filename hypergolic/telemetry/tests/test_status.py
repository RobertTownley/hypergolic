from __future__ import annotations

import threading
from types import SimpleNamespace

from hypergolic.telemetry.export_stats import ExportStats
from hypergolic.telemetry.status import _batch, telemetry_status


def test_export_stats_counts_results_and_errors() -> None:
    stats = ExportStats()
    stats.record(3, "SUCCESS", ok=True)
    stats.record_error(2, RuntimeError("boom"))
    snap = stats.snapshot()
    assert snap["calls"] == 2
    assert snap["items"] == 5
    assert snap["failures"] == 1
    assert snap["last_result"] == "exception"
    assert snap["last_error"] == "RuntimeError: boom"


def test_batch_reads_queue_and_worker_state() -> None:
    worker = threading.Thread(target=lambda: None)
    inner = SimpleNamespace(
        _queue=[1, 2], _max_queue_size=10, _worker_thread=worker,
        _shutdown=False, _pid=1,
    )
    state = _batch(SimpleNamespace(_batch_processor=inner))
    assert state == {
        "queued": 2, "max_queue": 10, "worker_alive": False,
        "shutdown": False, "created_in_pid": 1,
    }
    assert _batch(None) is None


def test_status_report_has_every_section() -> None:
    report = telemetry_status()
    assert set(report["exports"]) == {"spans", "logs", "metrics"}
    assert {"on_root", "seen", "emitted", "root_handlers"} <= set(report["log_handler"])
