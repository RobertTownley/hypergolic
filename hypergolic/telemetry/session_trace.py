"""One ``session.start`` trace per session, at an id derived from the session id.

A session lives for hours or days, so it is not one trace: startup
(``session.start``) and each ``turn`` are separate traces. Turns link back to
``session.start`` through a span link. The link needs the start span's ids, and
a turn can run days later in a new process, so the ids are a hash of the
session id instead of stored state: any process can rebuild them, and a tool
can open a session's start trace from the session id alone.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from opentelemetry.trace import Link, Span, SpanContext, TraceFlags

from hypergolic.telemetry.log_context import log_context

_forced_ids: ContextVar[tuple[int, int] | None] = ContextVar(
    "hypergolic_forced_span_ids", default=None
)


def session_trace_ids(session_id: str) -> tuple[int, int]:
    digest = hashlib.sha256(f"hypergolic.session:{session_id}".encode()).digest()
    trace_id = int.from_bytes(digest[:16], "big") or 1
    span_id = int.from_bytes(digest[16:24], "big") or 1
    return trace_id, span_id


def session_trace_id_hex(session_id: str) -> str:
    return format(session_trace_ids(session_id)[0], "032x")


class SessionIdGenerator(RandomIdGenerator):
    """Random ids, except for the one span started under ``_forced_ids``."""

    def generate_trace_id(self) -> int:
        forced = _forced_ids.get()
        return forced[0] if forced else super().generate_trace_id()

    def generate_span_id(self) -> int:
        forced = _forced_ids.get()
        if forced:
            _forced_ids.set(None)
            return forced[1]
        return super().generate_span_id()


def session_link(session_id: str) -> Link:
    trace_id, span_id = session_trace_ids(session_id)
    return Link(SpanContext(
        trace_id=trace_id, span_id=span_id, is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    ))


@contextmanager
def session_start_span(session_id: str, **attributes: str) -> Iterator[Span]:
    """Root span of the session's start trace; the caller's span becomes a link."""
    from hypergolic.telemetry.tracing import tracer

    caller = trace.get_current_span().get_span_context()
    token = _forced_ids.set(session_trace_ids(session_id))
    try:
        span = tracer.start_span(
            "session.start",
            context=otel_context.Context(),
            attributes={"session.id": session_id, **attributes},
            links=[Link(caller)] if caller.is_valid else None,
        )
    finally:
        _forced_ids.reset(token)
    with trace.use_span(span, end_on_exit=True), log_context(**{"session.id": session_id}):
        yield span
