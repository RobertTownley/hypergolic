"""Bring up the Postgres the test suite runs against.

Resolution order:

1. ``HYPERGOLIC_TEST_PG`` — explicit server URL (no database path).
2. ``postgres:5432`` — the sandbox sidecar (in-sandbox gate runs).
3. ``127.0.0.1:5432`` — a locally running server.
4. A throwaway host container (``hypergolic-postgres-test``) on a tmpfs.

A scratch database named ``hg_test_<pid>_<nonce>`` is created per run and
dropped at exit, so concurrent runs (a gate pytest next to a live session's)
never share state.
"""

from __future__ import annotations

import atexit
import os
import secrets
import shutil
import subprocess
import time
from contextlib import contextmanager

import psycopg
from psycopg import sql

TEST_CONTAINER = "hypergolic-postgres-test"
TEST_PORT = 54329
_CREDS = "hypergolic:hypergolic"
_SIDECAR = f"postgresql://{_CREDS}@postgres:5432"
_LOCAL = f"postgresql://{_CREDS}@127.0.0.1:5432"
_HOST_FALLBACK = f"postgresql://{_CREDS}@127.0.0.1:{TEST_PORT}"


def _connectable(server: str, timeout: int = 2) -> bool:
    try:
        psycopg.connect(f"{server}/postgres", connect_timeout=timeout).close()
        return True
    except psycopg.OperationalError:
        return False


def _wait_connectable(server: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _connectable(server):
            return
        time.sleep(0.5)
    raise RuntimeError(f"Test Postgres at {server} not reachable within {timeout:.0f}s")


def _ensure_host_container() -> None:
    if shutil.which("docker") is None:
        raise RuntimeError(
            "No test Postgres reachable (HYPERGOLIC_TEST_PG, postgres:5432, "
            "127.0.0.1:5432) and no docker binary to start one."
        )
    run = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", TEST_CONTAINER],
        capture_output=True, text=True,
    )
    if run.returncode == 0 and run.stdout.strip() == "true":
        return
    if run.returncode == 0:
        subprocess.run(["docker", "start", TEST_CONTAINER], capture_output=True, check=True)
        return
    subprocess.run(
        [
            "docker", "run", "-d",
            "--name", TEST_CONTAINER,
            "-p", f"127.0.0.1:{TEST_PORT}:5432",
            "--tmpfs", "/var/lib/postgresql/data",
            "-e", "POSTGRES_USER=hypergolic",
            "-e", "POSTGRES_PASSWORD=hypergolic",
            "-e", "POSTGRES_DB=hypergolic",
            "postgres:17-alpine",
            "postgres", "-c", "fsync=off", "-c", "synchronous_commit=off",
            "-c", "full_page_writes=off",
        ],
        capture_output=True, text=True, check=True,
    )


def _server_url() -> str:
    if explicit := os.environ.get("HYPERGOLIC_TEST_PG"):
        _wait_connectable(explicit)
        return explicit
    for server in (_SIDECAR, _LOCAL):
        if _connectable(server):
            return server
    _ensure_host_container()
    _wait_connectable(_HOST_FALLBACK)
    return _HOST_FALLBACK


def ensure_test_database() -> None:
    """Create this run's scratch DB and export it as HYPERGOLIC_DATABASE_URL."""
    server = _server_url()
    name = f"hg_test_{os.getpid()}_{secrets.token_hex(3)}"
    with psycopg.connect(f"{server}/postgres", autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

    def _drop() -> None:
        try:
            with psycopg.connect(f"{server}/postgres", autocommit=True) as conn:
                conn.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(name)
                    )
                )
        except psycopg.OperationalError:
            pass

    atexit.register(_drop)
    os.environ["HYPERGOLIC_DATABASE_URL"] = f"{server}/{name}"



@contextmanager
def scratch_database(suffix: str):
    """A second throwaway DB on this run's server (e.g. for migration tests)."""
    base = os.environ["HYPERGOLIC_DATABASE_URL"]
    server, _, _ = base.rpartition("/")
    name = f"hg_test_{os.getpid()}_{suffix}_{secrets.token_hex(3)}"
    with psycopg.connect(f"{server}/postgres", autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield f"{server}/{name}"
    finally:
        with psycopg.connect(f"{server}/postgres", autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                )
            )
