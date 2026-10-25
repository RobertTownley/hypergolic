"""Counters for one OTLP signal's exports, read by the telemetry status report.

The exporters are the only place that knows whether a batch left the process;
the OTLP exporter itself logs failures (which ``_NotExporterLogs`` keeps out of
Loki) but keeps no count, so a signal that never exports is otherwise silent.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class ExportStats:
    calls: int = 0
    items: int = 0
    failures: int = 0
    last_result: str = ""
    last_error: str = ""
    last_at: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, items: int, result: str, *, ok: bool) -> None:
        with self._lock:
            self.calls += 1
            self.items += items
            self.failures += 0 if ok else 1
            self.last_result = result
            self.last_at = time.time()

    def record_error(self, items: int, exc: BaseException) -> None:
        with self._lock:
            self.calls += 1
            self.items += items
            self.failures += 1
            self.last_result = "exception"
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            self.last_at = time.time()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "calls": self.calls,
                "items": self.items,
                "failures": self.failures,
                "last_result": self.last_result,
                "last_error": self.last_error,
                "seconds_since_last": (
                    round(time.time() - self.last_at, 1) if self.last_at else None
                ),
            }
