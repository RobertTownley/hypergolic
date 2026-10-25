"""What each sandbox exec runs and costs, for span attributes and metrics.

``exec.cpu_s`` is the container's CPU time across the exec, so it includes
anything else running in that container at the same time.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import time
from collections.abc import Awaitable

from opentelemetry import metrics
from opentelemetry.trace import Span

from hypergolic.system import docker_api
from hypergolic.telemetry.sandbox_metrics import PROJECT_LABEL, SERVICE_LABEL, cpu_seconds

_MEASURE_CPU_AFTER_S = 2.0
_SEGMENT = re.compile(r"&&|\|\||[;|\n]")
_WRAPPERS = frozenset({"cd", "env", "exec", "time", "timeout", "nice", "sudo", "uv", "run", "npx"})
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Segments that only set up the shell; the real program is in a later segment.
_SETUP = frozenset({"cd", "set", "export", "unset", "source", ".", "shopt", "trap", "umask", "true"})

_cpu_reads_enabled = False

_meter = metrics.get_meter("hypergolic")
_duration = _meter.create_histogram(
    "sandbox.exec.duration", unit="s", description="Wall time of one sandbox exec.",
    explicit_bucket_boundaries_advisory=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600],
)
_cpu = _meter.create_counter(
    "sandbox.exec.cpu", unit="s",
    description="Container CPU time during execs of 2s or more.",
)


def enable_cpu_reads() -> None:
    global _cpu_reads_enabled
    _cpu_reads_enabled = True


def _first_program(segment: str) -> str | None:
    try:
        words = shlex.split(segment)
    except ValueError:
        words = segment.split()
    for word in words:
        if _ASSIGNMENT.match(word) or word.startswith("-") or word.isdigit():
            continue
        name = os.path.basename(word)
        if name not in _WRAPPERS:
            return name
    return None


def program_of(command: str) -> str:
    for segment in _SEGMENT.split(command):
        words = segment.split()
        if not words or words[0] in _SETUP:
            continue
        if (name := _first_program(segment)) is not None:
            return name[:40]
    return "other"


def _container_cpu(project: str, service: str) -> float | None:
    found = docker_api.labeled_containers(f"{PROJECT_LABEL}={project}", f"{SERVICE_LABEL}={service}")
    return cpu_seconds(docker_api.container_stats(found[0]["Id"])) if found else None


async def _safe(read: Awaitable[float | None]) -> float | None:
    try:
        return await read
    except Exception:  # noqa: BLE001 - a failed read only drops the attribute
        return None


class ExecMeter:
    def __init__(self, span: Span, project: str, service: str, command: str) -> None:
        self._span, self._project, self._service = span, project, service
        self._attrs = {"sandbox.container": service, "exec.program": program_of(command)}
        span.set_attribute("exec.program", self._attrs["exec.program"])
        self._started = time.monotonic()
        self._before = (
            asyncio.ensure_future(_safe(self._read())) if _cpu_reads_enabled else None
        )

    def _read(self) -> Awaitable[float | None]:
        return asyncio.to_thread(_container_cpu, self._project, self._service)

    def abandon(self) -> None:
        if self._before is not None:
            self._before.cancel()

    async def finish(self) -> None:
        elapsed = time.monotonic() - self._started
        _duration.record(elapsed, self._attrs)
        if self._before is None:
            return
        if elapsed < _MEASURE_CPU_AFTER_S:
            self.abandon()
            return
        before, after = await self._before, await _safe(self._read())
        if before is not None and after is not None and after >= before:
            self._span.set_attribute("exec.cpu_s", round(after - before, 2))
            _cpu.add(after - before, self._attrs)
