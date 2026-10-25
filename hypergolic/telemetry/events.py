from __future__ import annotations

import logging

from opentelemetry import metrics

logger = logging.getLogger("hypergolic.events")
_counter = metrics.get_meter("hypergolic").create_counter(
    "hypergolic.events", description="Analytics events by name",
)

Attr = str | int | float | bool | None


def emit(name: str, *, session_id: str | None = None, **attrs: Attr) -> None:
    fields = {k: v for k, v in attrs.items() if v is not None}
    extra: dict[str, Attr] = {"event.name": name}
    extra.update({f"event.{k}": v for k, v in fields.items()})
    if session_id:
        extra["session.id"] = session_id
        fields = {"session": session_id, **fields}
    logger.info(
        "event %s%s", name, "".join(f" {k}={v}" for k, v in fields.items()), extra=extra,
    )
    _counter.add(1, {"event.name": name})
