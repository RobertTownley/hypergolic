"""Self-report of the telemetry pipeline, from inside the harness process.

macOS refuses ``sys.remote_exec``/``py-spy`` against the harness without root,
so the process reports its own SDK state instead. The report answers "is each
signal leaving the process, and if not, where does it stop": handler attached,
records reaching the handler, batch queue depth, worker thread alive, exports
attempted and their results.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry._logs import get_logger_provider

from hypergolic.config.settings import settings
from hypergolic.telemetry.startup import managed_backend
from hypergolic.telemetry.tracing import backend_ready, export_stats, installed


def _batch(processor: object | None) -> dict[str, Any] | None:
    """State of a Batch{Span,LogRecord}Processor (SDK-private; read only)."""
    inner = getattr(processor, "_batch_processor", None)
    if inner is None:
        return None
    worker = getattr(inner, "_worker_thread", None)
    return {
        "queued": len(getattr(inner, "_queue", ())),
        "max_queue": getattr(inner, "_max_queue_size", None),
        "worker_alive": worker.is_alive() if worker is not None else None,
        "shutdown": getattr(inner, "_shutdown", None),
        "created_in_pid": getattr(inner, "_pid", None),
    }


def _handler_desc(handler: logging.Handler) -> str:
    return f"{type(handler).__name__}({logging.getLevelName(handler.level)})"


def _log_handler() -> dict[str, Any]:
    handler = installed.get("log_handler")
    root = logging.getLogger()
    return {
        "installed": handler is not None,
        "on_root": handler in root.handlers,
        "seen": getattr(handler, "seen", None),
        "emitted": getattr(handler, "emitted", None),
        "root_level": logging.getLevelName(root.level),
        "root_handlers": [_handler_desc(h) for h in root.handlers],
        "hypergolic_effective_level": logging.getLevelName(
            logging.getLogger("hypergolic").getEffectiveLevel()
        ),
    }


def _global(current: object, ours: object | None) -> dict[str, Any]:
    return {"type": type(current).__name__, "is_ours": current is ours}


def telemetry_status() -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "endpoint": settings.HYPERGOLIC_OTEL_ENDPOINT,
        "managed_backend": managed_backend(),
        "backend_ready": backend_ready.is_set(),
        "providers": {
            "traces": _global(trace.get_tracer_provider(), installed.get("tracer_provider")),
            "metrics": _global(metrics.get_meter_provider(), installed.get("meter_provider")),
            "logs": _global(get_logger_provider(), installed.get("logger_provider")),
        },
        "queues": {
            "spans": _batch(installed.get("span_processor")),
            "logs": _batch(installed.get("log_processor")),
        },
        "exports": {name: stats.snapshot() for name, stats in export_stats.items()},
        "log_handler": _log_handler(),
    }
