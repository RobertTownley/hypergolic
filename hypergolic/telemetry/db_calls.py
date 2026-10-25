"""Which code sent each SQL query, on the span and as metrics.

SQLAlchemy's instrumentation records the statement but not the caller, and a
query run outside any turn or request becomes its own root trace with no
owner. ``DbCallerProcessor`` walks the stack when a SQL span starts and tags it
with the first ``hypergolic`` frame outside the DB layer — for ``run_db`` that
is the caller's sync ``fn``, which runs inside SQLAlchemy's greenlet. It also
counts queries and their time by caller and operation, so "is the app spamming
the DB, and from where?" is one metric query.
"""
from __future__ import annotations

import sys

from opentelemetry import context as otel_context
from opentelemetry import metrics
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

CALLER_ATTR = "code.function"
_SKIP_PREFIXES = ("hypergolic.db.", "hypergolic.telemetry.")

_queries = metrics.get_meter("hypergolic").create_counter(
    "db.client.queries", unit="{query}", description="SQL statements by caller",
)
_duration = metrics.get_meter("hypergolic").create_histogram(
    "db.client.query.duration", unit="s", description="SQL statement time by caller",
)


def query_caller() -> str:
    frame = sys._getframe(1)
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if module.startswith("hypergolic.") and not module.startswith(_SKIP_PREFIXES):
            return f"{module}.{frame.f_code.co_qualname}"
        frame = frame.f_back
    return "unknown"


def operation(span: ReadableSpan) -> str:
    """First SQL keyword, or the span name for ``connect``."""
    attrs = span.attributes or {}
    statement = attrs.get("db.statement") or attrs.get("db.query.text") or ""
    words = str(statement).split(maxsplit=1)
    return words[0].upper() if words else span.name


#: The instrumentation sets db.* attributes only after the span starts, so
#: SQL spans are recognised by the scope that created them.
_SQLALCHEMY_SCOPE = "opentelemetry.instrumentation.sqlalchemy"


def _is_sql(span: ReadableSpan) -> bool:
    scope = span.instrumentation_scope
    return scope is not None and scope.name == _SQLALCHEMY_SCOPE


class DbCallerProcessor(SpanProcessor):
    def on_start(
        self, span: Span, parent_context: otel_context.Context | None = None
    ) -> None:
        if _is_sql(span):
            span.set_attribute(CALLER_ATTR, query_caller())

    def on_end(self, span: ReadableSpan) -> None:
        if not _is_sql(span) or span.start_time is None or span.end_time is None:
            return
        attrs = span.attributes or {}
        labels = {
            CALLER_ATTR: str(attrs.get(CALLER_ATTR, "unknown")),
            "db.operation": operation(span),
            # A query with no parent span ran outside any turn or request.
            "db.root": span.parent is None,
        }
        _queries.add(1, labels)
        _duration.record((span.end_time - span.start_time) / 1e9, labels)
