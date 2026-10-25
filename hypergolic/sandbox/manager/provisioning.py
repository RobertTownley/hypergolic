"""Compose config parsing and per-session resolved-config provisioning.

Handles reading the canonical compose YAML, discovering exposed-port targets,
and writing the per-session "resolved" compose (with dynamic port publishing)
that `up` runs against.
"""

import hashlib
import logging
import re
from pathlib import Path

import yaml

from hypergolic.sandbox.manager import docker
from hypergolic.sandbox.manager.types import SandboxError

logger = logging.getLogger(__name__)

COMPOSE_PROJECT_PREFIX = "hg"


def _compose_project_name(session_id: str, sandbox_id: str) -> str:
    """Generate a unique compose project name for a sandbox."""
    safe_id = re.sub(r"[^a-z0-9]", "", sandbox_id.lower())
    short_session = re.sub(r"[^a-z0-9]", "", session_id.lower())[:12]
    return f"{COMPOSE_PROJECT_PREFIX}{safe_id}{short_session}"


def _config_hash(config_path: str) -> str:
    """Digest of the compiled canonical compose file; drift against the
    DBSandbox row's stored hash means the project config changed since `up`.
    A wiped config reads as drift; the locked path fails it gracefully."""
    try:
        return hashlib.sha256(Path(config_path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return "missing"


def config_declares_build(config_path: str) -> bool:
    """Does any service in this compose config build from a Dockerfile?"""
    try:
        config = _parse_config(config_path)
    except SandboxError:
        return False
    services = config.get("services") or {}
    return any("build" in (svc or {}) for svc in services.values())


def _parse_config(config_path: str) -> dict:
    """Parse a sandbox compose YAML file."""
    path = Path(config_path).expanduser()
    if not path.exists():
        raise SandboxError(f"Sandbox config not found: {path}")
    with open(path) as f:
        config = yaml.safe_load(f)
    if not config or "services" not in config:
        raise SandboxError(f"Invalid sandbox config (no services): {path}")
    return config


def _find_default_service(config: dict) -> str:
    """Find the default service from a compose config.

    Looks for hypergolic.default label, falls back to first non-proxy service.
    """
    services = config.get("services", {})
    for name, svc in services.items():
        labels = svc.get("labels", {})
        if isinstance(labels, dict) and labels.get("hypergolic.default") == "true":
            return name
        if isinstance(labels, list):
            for label in labels:
                if label == "hypergolic.default=true":
                    return name

    # Fall back to first non-proxy service
    for name, svc in services.items():
        labels = svc.get("labels", {})
        is_proxy = False
        if isinstance(labels, dict):
            is_proxy = labels.get("hypergolic.role") == "proxy"
        elif isinstance(labels, list):
            is_proxy = "hypergolic.role=proxy" in labels
        if not is_proxy:
            return name

    raise SandboxError("No suitable service found in sandbox config")

def _label_value(labels, key: str) -> str | None:
    """Read a compose label by key (labels may be a dict or a list of strings)."""
    if isinstance(labels, dict):
        val = labels.get(key)
        return str(val) if val is not None else None
    if isinstance(labels, list):
        prefix = f"{key}="
        for item in labels:
            if isinstance(item, str) and item.startswith(prefix):
                return item[len(prefix):]
    return None


_RESOLVED_PREFIX = ".hg-resolved-"


def _expose_targets(config: dict) -> dict[str, tuple[str, int]]:
    """Map exposed-port name -> (service, container_port) from expose labels."""
    targets: dict[str, tuple[str, int]] = {}
    for service, svc in config.get("services", {}).items():
        spec = _label_value(svc.get("labels", {}), "hypergolic.expose")
        if not spec:
            continue
        for entry in spec.split(","):
            name, _, cport = entry.partition("=")
            if name and cport.isdigit():
                targets[name] = (service, int(cport))
            elif entry.strip():
                logger.warning(
                    "Ignoring malformed hypergolic.expose entry %r on service %s",
                    entry, service,
                )
    return targets


def _inject_dynamic_port_publishing(config: dict, targets: dict[str, tuple[str, int]]) -> None:
    """Add a ``ports`` mapping per exposed port, letting Docker pick the host port.

    Using ``127.0.0.1::<cport>`` (empty host port) defers allocation to Docker,
    which avoids the TOCTOU race of pre-binding a port ourselves. The actual
    host port is read back after ``up`` via ``compose port``.
    """
    for service, cport in targets.values():
        svc = config["services"][service]
        ports = svc.setdefault("ports", [])
        mapping = f"127.0.0.1::{cport}"
        if mapping not in ports:
            ports.append(mapping)


def _resolved_config_path(canonical_path: str, compose_project: str) -> Path:
    """Stable per-session path for the resolved compose, beside the canonical one.

    Same directory so relative bind mounts (e.g. the generated ``squid.conf``)
    still resolve; deterministic so it survives for the whole session and is
    re-created idempotently on each start.
    """
    base = Path(canonical_path).expanduser().parent
    return base / f"{_RESOLVED_PREFIX}{compose_project}.compose.yaml"


def _cleanup_resolved_config(config_path: str | None) -> None:
    """Remove a per-session resolved compose file. Canonical configs are kept."""
    if not config_path:
        return
    if Path(config_path).name.startswith(_RESOLVED_PREFIX):
        try:
            Path(config_path).unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove resolved config %s", config_path, exc_info=True)


def _external_volume_names(config: dict) -> list[str]:
    """Names of external volumes the config references.

    Compose refuses to `up` when an ``external: true`` volume doesn't exist,
    so the manager creates these idempotently first. Shared cross-session
    volumes (:class:`~hypergolic.sandbox.model.Volume` with ``shared=True``)
    compile to exactly this shape.
    """
    names = []
    for vol_id, spec in (config.get("volumes") or {}).items():
        if isinstance(spec, dict) and spec.get("external"):
            names.append(spec.get("name") or vol_id)
    return names


async def _read_published_ports(
    compose_project: str, config_path: str, targets: dict[str, tuple[str, int]]
) -> dict[str, int]:
    """Read Docker-assigned host ports after ``up`` via ``compose port``."""
    port_map: dict[str, int] = {}
    for name, (service, cport) in targets.items():
        result = await docker._run_compose(
            "port", service, str(cport),
            project_name=compose_project,
            config_path=config_path,
            timeout=15,
        )
        # Output looks like "127.0.0.1:54321"; take the trailing port.
        text = result.stdout.strip().splitlines()
        if result.returncode == 0 and text:
            tail = text[-1].rsplit(":", 1)
            if len(tail) == 2 and tail[1].isdigit():
                port_map[name] = int(tail[1])
    return port_map


def _prepare_run_config(
    canonical_path: str, compose_project: str
) -> tuple[str, dict[str, tuple[str, int]], list[str]]:
    """Build the config path to run `up` against, plus what `up` needs first.

    When the config declares dynamic ports, publish them into a resolved config
    written beside the canonical one and return its path; otherwise return the
    canonical path unchanged. Returns ``(run_path, targets, external_volumes)``.
    """
    config = _parse_config(canonical_path)
    targets = _expose_targets(config)
    external_volumes = _external_volume_names(config)
    if not targets:
        return canonical_path, targets, external_volumes
    _inject_dynamic_port_publishing(config, targets)
    run_path = str(_resolved_config_path(canonical_path, compose_project))
    with open(run_path, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)
    return run_path, targets, external_volumes
