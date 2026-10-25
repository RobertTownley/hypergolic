from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation


def _cpu(_options: CallbackOptions) -> Iterable[Observation]:
    times = os.times()
    return [Observation(times.user + times.system)]


def _rss(_options: CallbackOptions) -> Iterable[Observation]:
    result = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True, timeout=5,
    )
    text = result.stdout.strip()
    return [Observation(int(text) * 1024)] if text.isdigit() else []


def register_process_metrics(meter: metrics.Meter) -> None:
    meter.create_observable_counter(
        "harness.cpu.time", [_cpu], unit="s",
        description="CPU time of the harness server process.",
    )
    meter.create_observable_gauge(
        "harness.memory.rss", [_rss], unit="By",
        description="Resident memory of the harness server process.",
    )
