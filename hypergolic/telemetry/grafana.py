"""Tempo, Loki, and Prometheus through Grafana.

otel-lgtm provisions each store as a Grafana datasource; the datasource proxy
is the one URL that reaches all three.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from hypergolic.config.settings import settings


def datasource_get(datasource: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{settings.HYPERGOLIC_GRAFANA_URL}/api/datasources/proxy/uid/{datasource}{path}{query}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def prom_query(promql: str) -> list[dict[str, Any]]:
    return datasource_get("prometheus", "/api/v1/query", {"query": promql})["data"]["result"]


def prom_range(promql: str, start: float, end: float, step: int) -> list[dict[str, Any]]:
    params = {"query": promql, "start": start, "end": end, "step": step}
    return datasource_get("prometheus", "/api/v1/query_range", params)["data"]["result"]
