"""CPU, memory, and process count for sandbox containers, as OTel instruments.

The metric reader's export tick drives the poll: each tick lists the labeled
containers and reads one stats snapshot each from the Docker API, on the
reader's own thread, never on the event loop. Every harness container carries
the ``hypergolic.session`` label, so one key-only filter finds them all and
names their session.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

from hypergolic.enums import SessionStatus
from hypergolic.sandbox.model.constants import SESSION_LABEL
from hypergolic.system import docker_api

#: The instruments share one sample per export tick; one callback each, one poll.
_SAMPLE_TTL_S = 5.0

PROJECT_LABEL = "com.docker.compose.project"
SERVICE_LABEL = "com.docker.compose.service"

_IDLE = frozenset({
    SessionStatus.IDLE, SessionStatus.ERROR, SessionStatus.CONCLUDED, SessionStatus.INTERRUPTED,
})


@dataclass(frozen=True)
class ContainerSample:
    session_id: str
    compose_project: str
    service: str
    session_state: str
    cpu_seconds: float
    throttled_seconds: float
    memory_bytes: float
    memory_limit_bytes: float
    pids: int

    def attributes(self) -> dict[str, str]:
        return {
            "session.id": self.session_id,
            "session.state": self.session_state,
            "sandbox.compose_project": self.compose_project,
            "sandbox.container": self.service,
        }


def cpu_seconds(stats: dict[str, Any]) -> float:
    return stats["cpu_stats"]["cpu_usage"]["total_usage"] / 1e9


def parse_stats(labels: dict[str, str], state: str, stats: dict[str, Any]) -> ContainerSample:
    memory = stats.get("memory_stats", {})
    throttling = stats["cpu_stats"].get("throttling_data", {})
    return ContainerSample(
        session_id=labels[SESSION_LABEL],
        compose_project=labels.get(PROJECT_LABEL, ""),
        service=labels.get(SERVICE_LABEL, ""),
        session_state=state,
        cpu_seconds=cpu_seconds(stats),
        throttled_seconds=throttling.get("throttled_time", 0) / 1e9,
        memory_bytes=memory.get("usage", 0) - memory.get("stats", {}).get("inactive_file", 0),
        memory_limit_bytes=memory.get("limit", 0),
        pids=stats.get("pids_stats", {}).get("current", 0),
    )


def session_state(status: str) -> str:
    return "idle" if SessionStatus(status) in _IDLE else "active"


def session_states(session_ids: set[str]) -> dict[str, str]:
    from sqlalchemy import select

    from hypergolic.db.engine import get_db
    from hypergolic.db.models import DBSession

    with get_db() as db:
        rows = db.execute(
            select(DBSession.id, DBSession.status).where(DBSession.id.in_(session_ids))
        ).all()
    return {sid: session_state(status) for sid, status in rows}


def _poll() -> list[ContainerSample]:
    containers = [
        c for c in docker_api.labeled_containers(SESSION_LABEL) if c["Labels"].get(SESSION_LABEL)
    ]
    if not containers:
        return []
    states = session_states({c["Labels"][SESSION_LABEL] for c in containers})
    return [
        parse_stats(
            c["Labels"], states.get(c["Labels"][SESSION_LABEL], "gone"),
            docker_api.container_stats(c["Id"]),
        )
        for c in containers
    ]


class _Sampler:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._at = 0.0
        self._samples: list[ContainerSample] = []

    def samples(self) -> list[ContainerSample]:
        with self._lock:
            if time.monotonic() - self._at > _SAMPLE_TTL_S:
                try:
                    self._samples = _poll()
                except Exception:  # noqa: BLE001 - a failed poll is a gap, not a crash
                    self._samples = []
                self._at = time.monotonic()
            return self._samples


_INSTRUMENTS = (
    ("create_observable_counter", "sandbox.cpu.time", "cpu_seconds", "s",
     "Container CPU time; rate() of 1 is one full core."),
    ("create_observable_counter", "sandbox.cpu.throttled", "throttled_seconds", "s",
     "Time the container's CPU limit held it back."),
    ("create_observable_gauge", "sandbox.memory.usage", "memory_bytes", "By",
     "Container memory use, without reclaimable page cache."),
    ("create_observable_gauge", "sandbox.memory.limit", "memory_limit_bytes", "By",
     "Container memory limit; the VM's memory when unlimited."),
    ("create_observable_gauge", "sandbox.pids", "pids", "{process}",
     "Processes in the container."),
)


def register_sandbox_gauges(meter: metrics.Meter) -> None:
    sampler = _Sampler()

    def observe(field: str):
        def callback(_options: CallbackOptions) -> Iterable[Observation]:
            return [Observation(getattr(s, field), s.attributes()) for s in sampler.samples()]
        return callback

    for factory, name, field, unit, description in _INSTRUMENTS:
        getattr(meter, factory)(name, [observe(field)], unit=unit, description=description)
