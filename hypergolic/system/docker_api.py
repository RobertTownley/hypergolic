from __future__ import annotations

import functools
import json
import os
from typing import Any

import httpx2

from hypergolic.system.docker import docker

_UNIX = "unix://"


@functools.cache
def _socket_path() -> str:
    host = os.environ.get("DOCKER_HOST") or docker(
        "context", "inspect", "--format", "{{.Endpoints.docker.Host}}", timeout=10
    ).stdout.strip()
    if not host.startswith(_UNIX):
        raise RuntimeError(f"Docker endpoint is not a unix socket: {host!r}")
    return host.removeprefix(_UNIX)


@functools.cache
def _client() -> httpx2.Client:
    return httpx2.Client(
        transport=httpx2.HTTPTransport(uds=_socket_path()),
        base_url="http://docker",
        timeout=10,
    )


def get(path: str, **params: Any) -> Any:
    response = _client().get(path, params=params)
    response.raise_for_status()
    return response.json()


def labeled_containers(*labels: str) -> list[dict[str, Any]]:
    return get("/containers/json", filters=json.dumps({"label": list(labels)}))


def container_stats(container_id: str) -> dict[str, Any]:
    return get(f"/containers/{container_id}/stats", stream="false", **{"one-shot": "true"})
