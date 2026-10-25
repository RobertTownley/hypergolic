from __future__ import annotations

from urllib.parse import urlsplit

from hypergolic.config.settings import DEFAULT_GRAFANA_URL, DEFAULT_OTEL_ENDPOINT
from hypergolic.system.docker import ensure_container

LGTM_IMAGE = "grafana/otel-lgtm:0.33.1"
LGTM_CONTAINER = "hypergolic-otel-lgtm"
LGTM_VOLUME = "hypergolic-otel-data"
OTLP_PORT = urlsplit(DEFAULT_OTEL_ENDPOINT).port
GRAFANA_PORT = urlsplit(DEFAULT_GRAFANA_URL).port


def ensure_telemetry_backend() -> None:
    ensure_container(LGTM_CONTAINER, [
        "-p", f"127.0.0.1:{OTLP_PORT}:4318",
        "-p", f"127.0.0.1:{GRAFANA_PORT}:3000",
        "-v", f"{LGTM_VOLUME}:/data",
        LGTM_IMAGE,
    ])
