from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib.metadata import version as pkg_version

from opentelemetry import context as otel_context
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry._logs import get_logger_provider, set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler, ReadableLogRecord
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    LogRecordExporter,
    LogRecordExportResult,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricExportResult,
    MetricsData,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from hypergolic.config.settings import settings
from hypergolic.telemetry.db_calls import DbCallerProcessor
from hypergolic.telemetry.export_stats import ExportStats
from hypergolic.telemetry.log_context import ContextFilter
from hypergolic.telemetry.exec_metrics import enable_cpu_reads
from hypergolic.telemetry.process_metrics import register_process_metrics
from hypergolic.telemetry.sandbox_metrics import register_sandbox_gauges
from hypergolic.telemetry.session_trace import SessionIdGenerator

tracer = trace.get_tracer("hypergolic")

#: Also the sandbox resource poll period (see sandbox_metrics).
METRIC_INTERVAL_MS = 15_000
#: Launch spans wait in memory while a first-run image pull finishes; the
#: SDK default (2048) overflows during a busy resume.
SPAN_QUEUE_SIZE = 32_768
#: Upper bound on holding the export thread for the backend; after this the
#: exporter's own retry/drop behaviour takes over.
BACKEND_WAIT_S = 600.0

@contextmanager
def root_span(
    name: str, *, links: Sequence[trace.Link] = (), **attributes: str,
) -> Iterator[trace.Span]:
    """Start a new trace, linked to (not nested under) the current span.

    For work that outlives or is independent of whatever scheduled it — a
    turn started from a WebSocket message or a parent's dispatch tool call, a
    reap kicked by session creation. Nesting would fold hours of that work
    into the scheduler's trace.
    """
    caller = trace.get_current_span().get_span_context()
    all_links = [*links, *([trace.Link(caller)] if caller.is_valid else [])]
    with tracer.start_as_current_span(
        name, context=otel_context.Context(), attributes=attributes,
        links=all_links,
    ) as span:
        yield span


#: Set once something can accept OTLP: immediately for a configured endpoint,
#: after the managed container is up otherwise.
backend_ready = threading.Event()

#: Per-signal export counters and the SDK objects this module installed, for
#: ``hypergolic.telemetry.status``. Holding our own references (not reading the
#: global providers) is what lets the report notice a provider replaced later.
export_stats = {"spans": ExportStats(), "logs": ExportStats(), "metrics": ExportStats()}
installed: dict[str, object] = {}


class _GatedExporter(SpanExporter):
    """Holds the first export until the backend exists.

    The OTLP exporter retries for ~10 s and then drops the batch, so without
    the gate every span from process launch until otel-lgtm answers is lost.
    Blocking the batch worker thread is safe: new spans keep queueing.
    """

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        backend_ready.wait(BACKEND_WAIT_S)
        stats = export_stats["spans"]
        try:
            result = self._inner.export(spans)
        except Exception as exc:
            stats.record_error(len(spans), exc)
            raise
        stats.record(len(spans), result.name, ok=result is SpanExportResult.SUCCESS)
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


class _GatedLogExporter(LogRecordExporter):
    """Same gate as spans: launch logs wait for the backend, not the void."""

    def __init__(self, inner: LogRecordExporter) -> None:
        self._inner = inner

    def export(self, batch: Sequence[ReadableLogRecord]) -> LogRecordExportResult:
        backend_ready.wait(BACKEND_WAIT_S)
        stats = export_stats["logs"]
        try:
            result = self._inner.export(batch)
        except Exception as exc:
            stats.record_error(len(batch), exc)
            raise
        stats.record(len(batch), result.name, ok=result is LogRecordExportResult.SUCCESS)
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 10_000) -> bool:
        return self._inner.force_flush(timeout_millis)


class _CountingMetricExporter(OTLPMetricExporter):
    def export(
        self, metrics_data: MetricsData, timeout_millis: float | None = 10_000,
        **kwargs: object,
    ) -> MetricExportResult:
        stats = export_stats["metrics"]
        items = len(metrics_data.resource_metrics)
        try:
            result = super().export(metrics_data, timeout_millis, **kwargs)
        except Exception as exc:
            stats.record_error(items, exc)
            raise
        stats.record(items, result.name, ok=result is MetricExportResult.SUCCESS)
        return result


class _CountingLoggingHandler(LoggingHandler):
    """Counts records offered (``seen``) and past the filters (``emitted``)."""

    seen = 0
    emitted = 0

    def handle(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        self.seen += 1
        return bool(super().handle(record))

    def emit(self, record: logging.LogRecord) -> None:
        self.emitted += 1
        super().emit(record)


class _NotExporterLogs(logging.Filter):
    """The exporter's own failure logs must not feed back into the exporter."""

    _PREFIXES = ("opentelemetry", "urllib3")

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(self._PREFIXES)


def _setup_logs(resource: Resource, endpoint: str) -> None:
    provider = LoggerProvider(resource=resource)
    processor = BatchLogRecordProcessor(
        _GatedLogExporter(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs")),
        max_queue_size=SPAN_QUEUE_SIZE,
    )
    provider.add_log_record_processor(processor)
    set_logger_provider(provider)
    handler = _CountingLoggingHandler(level=logging.INFO, logger_provider=provider)
    installed.update(
        logger_provider=provider, log_processor=processor, log_handler=handler
    )
    handler.addFilter(_NotExporterLogs())
    handler.addFilter(ContextFilter())
    logging.getLogger().addHandler(handler)


def setup_telemetry() -> None:
    resource = Resource.create(
        {"service.name": "hypergolic", "service.version": pkg_version("hypergolic")}
    )
    endpoint = settings.HYPERGOLIC_OTEL_ENDPOINT
    provider = TracerProvider(resource=resource, id_generator=SessionIdGenerator())
    exporter = _GatedExporter(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    provider.add_span_processor(DbCallerProcessor())
    span_processor = BatchSpanProcessor(exporter, max_queue_size=SPAN_QUEUE_SIZE)
    provider.add_span_processor(span_processor)
    trace.set_tracer_provider(provider)
    installed.update(tracer_provider=provider, span_processor=span_processor)

    reader = PeriodicExportingMetricReader(
        _CountingMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
        export_interval_millis=METRIC_INTERVAL_MS,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)
    installed.update(meter_provider=meter_provider)
    register_sandbox_gauges(meter_provider.get_meter("hypergolic"))
    register_process_metrics(meter_provider.get_meter("hypergolic"))
    enable_cpu_reads()
    _setup_logs(resource, endpoint)


def shutdown_telemetry() -> None:
    """Stop exporting. Spans started afterwards are dropped, not queued."""
    backend_ready.set()  # release a gated export so shutdown can drain
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()
    meter_provider = metrics.get_meter_provider()
    if isinstance(meter_provider, MeterProvider):
        meter_provider.shutdown()
    logger_provider = get_logger_provider()
    if isinstance(logger_provider, LoggerProvider):
        logger_provider.shutdown()
