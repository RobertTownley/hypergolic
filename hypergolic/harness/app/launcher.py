from __future__ import annotations

import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from typing import TYPE_CHECKING

import uvicorn
import webview
from opentelemetry import trace
from rich.console import Console
from rich.prompt import Confirm

from hypergolic.auth import init_bootstrap_token
from hypergolic.cli.setup import run_migrations
from hypergolic.db import container as db_container
from hypergolic.system.docker import ContainerError
from hypergolic.config.settings import settings
from hypergolic.logging import uvicorn_log_config
from hypergolic.telemetry.startup import (
    set_launch_span,
    start_telemetry,
    start_telemetry_backend,
)
from hypergolic.telemetry.tracing import tracer

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App


def _redact_url(url: str) -> str:
    """Strip any password from a DB URL before it reaches the console."""
    parsed = urllib.parse.urlsplit(url)
    if not parsed.password:
        return url
    netloc = parsed.netloc.replace(f":{parsed.password}", ":***", 1)
    return urllib.parse.urlunsplit(parsed._replace(netloc=netloc))


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    health_url = f"http://{host}:{port}/api/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(health_url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass
        time.sleep(0.1)
    return False


def _ensure_database(console: Console) -> bool:
    """Bring up the database before the server starts.

    An explicit HYPERGOLIC_DATABASE_URL (env or .env) points at
    externally-managed Postgres; otherwise Hypergolic runs its own
    container, starting the Docker desktop app first if the daemon is down.
    """
    if "HYPERGOLIC_DATABASE_URL" in settings.model_fields_set:
        console.print(
            f"[dim]Using configured database: "
            f"{_redact_url(settings.HYPERGOLIC_DATABASE_URL)}[/]"
        )
        return True

    if not db_container.docker_running():
        console.print("Docker isn't running — sessions and the database need it.")
        if not sys.stdin.isatty() or not Confirm.ask("Start it now?", default=True):
            console.print("[red]Error:[/] Cannot run without Docker.")
            return False
        if not db_container.start_docker_app():
            console.print(
                "[red]Error:[/] Couldn't launch OrbStack or Docker Desktop. "
                "Start your container runtime manually and retry."
            )
            return False
        console.print("[dim]Waiting for Docker daemon…[/]")
        if not db_container.wait_for_docker():
            console.print("[red]Error:[/] Docker did not come up within 90s.")
            return False

    try:
        db_container.ensure_postgres()
    except ContainerError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return False
    return True


def _start_server(app: App, console: Console) -> str | None:
    """Database, migrations, and the uvicorn thread; returns the UI URL."""
    app._expand_paths()

    with tracer.start_as_current_span("postgres.ensure"):
        if not _ensure_database(console):
            return None

    start_telemetry_backend()
    with tracer.start_as_current_span("migrations"):
        run_migrations()

    bootstrap_token = init_bootstrap_token()
    host = "127.0.0.1"
    port = settings.HYPERGOLIC_PORT
    url = f"http://{host}:{port}?token={bootstrap_token}"

    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": "hypergolic.api:app",
            "host": host,
            "port": port,
            "log_level": "info",
            "log_config": uvicorn_log_config(),
        },
        daemon=True,
    )
    server_thread.start()

    with tracer.start_as_current_span("server.wait_ready"):
        if not _wait_for_server(host, port):
            console.print("[red]Error:[/] Server failed to start within timeout.")
            return None
    return url


def launch(app: App, *, safe: bool = False) -> None:
    console = Console()

    start_telemetry()
    startup = tracer.start_span("harness.startup", attributes={"harness.safe_mode": safe})
    set_launch_span(startup)
    try:
        with trace.use_span(startup):
            url = _start_server(app, console)
    finally:
        startup.end()
    if url is None:
        return

    if safe:
        console.print(
            "[yellow]\u26a0 Running in safe mode \u2014 base tools only, no user config[/]"
        )

    largest_screen = max(webview.screens, key=lambda s: s.width * s.height)
    window = webview.create_window(
        "Hypergolic",
        url,
        screen=largest_screen,
        background_color="#0a0a0f",
        maximized=True,
        text_select=True,
    )

    def _maximize():
        if window:
            window.move(0, 0)
            window.resize(largest_screen.width, largest_screen.height)

    webview.start(func=_maximize, debug=False)
