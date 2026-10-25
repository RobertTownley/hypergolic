"""Event-loop lag monitor.

The whole server — every session's turn loop, streaming, and websocket
traffic — shares one asyncio event loop. Any sync work that sneaks into an
async path stalls *all* sessions and every API response at once. An async
heartbeat detects the stall; a watchdog thread samples the loop thread's
stack mid-stall so the warning names the blocking call in one line.
"""

import asyncio
import logging
import os
import sys
import threading
import time
from types import FrameType

from opentelemetry import metrics

from hypergolic.telemetry.tracing import tracer

logger = logging.getLogger(__name__)

_INTERVAL_S = 0.25
_WARN_THRESHOLD_S = 0.25
_lag = metrics.get_meter("hypergolic").create_histogram(
    "event_loop.lag", unit="s", description="Delay of the event-loop heartbeat past its schedule.",
    explicit_bucket_boundaries_advisory=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
)
_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Beat:
    def __init__(self) -> None:
        self.at = time.monotonic()
        self.culprit: str | None = None


def _label(frame: FrameType) -> str:
    path = frame.f_code.co_filename
    if path.startswith(_PKG_DIR):
        short = os.path.relpath(path, os.path.dirname(_PKG_DIR))
    else:
        short = os.path.join(*path.split(os.sep)[-2:])
    return f"{short}:{frame.f_lineno} {frame.f_code.co_name}"


def _where(frame: FrameType | None) -> str | None:
    inner = frame
    own = None
    while frame is not None and own is None:
        if frame.f_code.co_filename.startswith(_PKG_DIR) and frame.f_code.co_filename != __file__:
            own = frame
        frame = frame.f_back
    if inner is None:
        return None
    if own is None or own is inner:
        return _label(inner)
    return f"{_label(own)} → {_label(inner)}"


def _watch(beat: _Beat, loop_tid: int, deadline: float, stop: threading.Event) -> None:
    while not stop.wait(deadline / 4):
        if beat.culprit is None and time.monotonic() - beat.at > deadline:
            beat.culprit = _where(sys._current_frames().get(loop_tid))


def _report_stall(lag: float, culprit: str) -> None:
    logger.warning("Event loop stalled for %.0fms in %s", lag * 1000, culprit)
    end = time.time_ns()
    span = tracer.start_span(
        "event_loop.stall",
        start_time=end - int(lag * 1e9),
        attributes={"stall.culprit": culprit, "stall.ms": round(lag * 1000)},
    )
    span.end(end_time=end)


def start_loop_lag_monitor(
    interval: float = _INTERVAL_S,
    threshold: float = _WARN_THRESHOLD_S,
) -> asyncio.Task[None]:
    beat = _Beat()
    stop = threading.Event()

    async def _monitor() -> None:
        try:
            while True:
                beat.at = time.monotonic()
                beat.culprit = None
                await asyncio.sleep(interval)
                lag = time.monotonic() - beat.at - interval
                _lag.record(max(lag, 0.0))
                if lag > threshold:
                    _report_stall(lag, beat.culprit or "unknown")
        finally:
            stop.set()

    threading.Thread(
        target=_watch,
        args=(beat, threading.get_ident(), interval + threshold, stop),
        name="loop-lag-watchdog",
        daemon=True,
    ).start()
    return asyncio.create_task(_monitor(), name="loop-lag-monitor")
