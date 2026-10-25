"""Managed Postgres container: the default Hypergolic database.

When ``HYPERGOLIC_DATABASE_URL`` is not explicitly configured, Hypergolic
runs its database as a pinned Postgres container on the host — Docker is
already a hard prerequisite for session sandboxes, so the DB rides the same
runtime. Data lives on a named volume; the container is plain ``docker run``
(no compose labels), which keeps it invisible to the sandbox reaper.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

from sqlalchemy.engine import make_url

from hypergolic.config.settings import DEFAULT_DATABASE_URL
from hypergolic.system.docker import ContainerError, docker, ensure_container

PG_IMAGE = "postgres:17-alpine"
PG_CONTAINER = "hypergolic-postgres"
PG_VOLUME = "hypergolic-pgdata"
_url = make_url(DEFAULT_DATABASE_URL)
assert _url.port and _url.username and _url.password and _url.database
PG_PORT: int = _url.port
PG_USER: str = _url.username
PG_PASSWORD: str = _url.password
PG_DB: str = _url.database


def docker_running() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return docker("info", timeout=10).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def start_docker_app() -> bool:
    """Best-effort launch of the container runtime's desktop app (macOS)."""
    if sys.platform != "darwin":
        return False
    return any(
        subprocess.run(["open", "-g", "-a", app], capture_output=True).returncode == 0
        for app in ("OrbStack", "Docker")
    )


def wait_for_docker(timeout: float = 90) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if docker_running():
            return True
        time.sleep(1)
    return False


def ensure_postgres() -> None:
    """Idempotently bring up the managed Postgres container and await readiness."""
    ensure_container(PG_CONTAINER, [
        "-p", f"127.0.0.1:{PG_PORT}:5432",
        "-v", f"{PG_VOLUME}:/var/lib/postgresql/data",
        "-e", f"POSTGRES_USER={PG_USER}",
        "-e", f"POSTGRES_PASSWORD={PG_PASSWORD}",
        "-e", f"POSTGRES_DB={PG_DB}",
        PG_IMAGE,
    ])
    _wait_ready()


def _wait_ready(timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = docker("exec", PG_CONTAINER, "pg_isready", "-U", PG_USER, "-d", PG_DB)
        if probe.returncode == 0:
            return
        time.sleep(0.5)
    raise ContainerError(
        f"{PG_CONTAINER} did not become ready within {timeout:.0f}s"
    )
