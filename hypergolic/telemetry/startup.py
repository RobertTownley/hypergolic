"""Telemetry comes up in two halves so launch work is never lost.

``start_telemetry`` installs the SDK providers synchronously at the top of
``launch`` — before Postgres, migrations, or session resume — so every span
from process start onward is recorded. Exports wait on ``backend_ready``.
``start_telemetry_backend`` runs once Docker is known to be up and starts the
managed otel-lgtm container in the background, because a first-run image
pull takes minutes.
"""
from __future__ import annotations

import logging
import threading

from opentelemetry import context as otel_context
from opentelemetry.trace import Span, set_span_in_context

from hypergolic.config.settings import settings
from hypergolic.system.docker import ContainerError
from hypergolic.telemetry.container import ensure_telemetry_backend
from hypergolic.telemetry.tracing import (
    backend_ready,
    setup_telemetry,
    shutdown_telemetry,
)

logger = logging.getLogger(__name__)

#: The ``harness.startup`` span, for the server thread's lifespan to parent
#: under. Passed explicitly: copying the launch context into the uvicorn
#: thread would parent every request and turn under startup.
_launch_context: otel_context.Context | None = None


def set_launch_span(span: Span) -> None:
    global _launch_context
    _launch_context = set_span_in_context(span)


def launch_context() -> otel_context.Context | None:
    return _launch_context


def managed_backend() -> bool:
    return "HYPERGOLIC_OTEL_ENDPOINT" not in settings.model_fields_set


def _bring_up_backend() -> None:
    try:
        ensure_telemetry_backend()
    except ContainerError as exc:
        # Nothing will ever accept the buffered spans; stop exporting rather
        # than log a connection error every batch for the life of the process.
        logger.warning("Telemetry disabled: %s", exc)
        shutdown_telemetry()
        return
    backend_ready.set()


def start_telemetry() -> None:
    setup_telemetry()
    if not managed_backend():
        backend_ready.set()


def start_telemetry_backend() -> None:
    if managed_backend():
        threading.Thread(
            target=_bring_up_backend, name="telemetry-backend", daemon=True
        ).start()
