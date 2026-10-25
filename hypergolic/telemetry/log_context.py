"""Session and trace ids on every log line.

A ``ContextVar`` carries fields (``session.id``) set where a turn or session
start begins; ``ContextFilter`` copies them, plus the current trace and span
ids, onto each record. The file handlers print them as ``hg_context``; the
OTel handler sends them to Loki as attributes, so Grafana can jump between a
slow span and its log lines.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from opentelemetry import trace

_fields: ContextVar[dict[str, str]] = ContextVar("hypergolic_log_context", default={})


@contextmanager
def log_context(**fields: str) -> Iterator[None]:
    token = _fields.set({**_fields.get(), **fields})
    try:
        yield
    finally:
        _fields.reset(token)


class ContextFilter(logging.Filter):
    """Never drops a record; only annotates it. Idempotent across handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "hg_context"):
            return True
        fields = dict(_fields.get())
        span = trace.get_current_span().get_span_context()
        if span.is_valid:
            fields["trace_id"] = format(span.trace_id, "032x")
            fields["span_id"] = format(span.span_id, "016x")
        for key, value in fields.items():
            setattr(record, key, value)
        record.hg_context = "".join(f" {k}={v}" for k, v in fields.items())
        return True
