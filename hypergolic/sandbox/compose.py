"""Compile a :class:`~hypergolic.sandbox.model.ProjectSandbox` to Docker Compose.

Split out of :mod:`hypergolic.sandbox.model` so the authoring model (pydantic
types + validation) stays separate from the compose/squid compilation backend.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from hypergolic.sandbox.exec_env import BROKER_HOST, server_port
from hypergolic.git.quarantine import quarantine_mount
from hypergolic.git.sandbox_repo import (
    GITDIR_VOLUME,
    GITDIR_MOUNT_ROOT,
    REPO_APP,
    REPO_HARNESS,
    REPO_SHARED,
)
from hypergolic.sandbox.model.constants import (
    EGRESS_EXTERNAL_NETWORK,
    EGRESS_INTERNAL_NETWORK,
    EGRESS_PROXY_PORT,
    EGRESS_PROXY_SERVICE,
    HARNESS_ENV,
    HARNESS_MOUNT,
    HOST_OBJECTS_APP_ENV,
    HOST_REPO_APP_ENV,
    HOST_REPO_HARNESS_ENV,
    HOST_REPO_SHARED_ENV,
    PACKAGE_ENV,
    PACKAGE_MOUNT,
    QUARANTINE_APP_ENV,
    QUARANTINE_HARNESS_ENV,
    QUARANTINE_SHARED_ENV,
    SESSION_ENV,
    SESSION_LABEL,
    SHARED_ENV,
    SHARED_MOUNT,
    SQUID_IMAGE,
    TOOLS_ENV,
    TOOLS_MOUNT,
    WORKSPACE_ENV,
    WORKSPACE_MOUNT,
)
from hypergolic.sandbox.model.containers import Image
from hypergolic.sandbox.model.egress import Egress, EgressMode
from hypergolic.sandbox.model.sandbox import REQUIRED_BUILD_STEPS, ProjectSandbox


def built_image_tag(sandbox_id: str, container_id: str) -> str:
    """Stable image tag for a container Hypergolic builds from a Dockerfile.

    Keyed on the sandbox config, not the compose project, so all sessions of a
    project share one image. A rebuild only happens when the server restarts
    (see the startup prebuild) or when a cold start finds the tag missing.
    """
    slug = lambda s: re.sub(r"[^a-z0-9_.-]", "", s.lower())  # noqa: E731
    return f"hg-{slug(sandbox_id)}-{slug(container_id)}:latest"


#: Relative to GENERATED_SANDBOX_DIR; write_compose creates it empty so builds
#: with no authored context don't ship the whole sandboxes dir to the daemon.
EMPTY_BUILD_CONTEXT = "hg-empty-context"


def _dockerfile(img: Image, required_steps: str) -> str:
    """Render an Image: FROM, authored steps, required steps (as root), USER.

    Hypergolic owning FROM and USER is what makes the required-steps insertion
    structural — it always lands after the authored steps and before any
    non-root final user.
    """
    parts = [f"FROM {img.base}", *img.steps]
    if required_steps:
        parts.append(required_steps.rstrip("\n"))
    if img.user:
        parts.append(f"USER {img.user}")
    return "\n".join(parts) + "\n"


def _build_section(img: Image, required_steps: str) -> dict[str, Any]:
    build: dict[str, Any] = {
        "context": img.context or EMPTY_BUILD_CONTEXT,
        "dockerfile_inline": _dockerfile(img, required_steps),
    }
    if img.args:
        build["args"] = dict(img.args)
    if img.additional_contexts:
        build["additional_contexts"] = dict(img.additional_contexts)
    return build


def render_squid_conf(egress: Egress) -> str | None:
    """Render a squid.conf for this policy, or None when unrestricted.

    Domain-level allowlisting only (no TLS interception): squid sees
    host+port over CONNECT, so allow rules key on ``dstdomain``.

    The harness itself is always allowed. Restricted services sit on an
    internal network, so the ``/tools/bin`` shims can neither resolve nor route
    to the host directly — their plain-HTTP broker call has to travel through
    squid, and squid refuses a port outside ``Safe_ports`` before any allow rule
    is consulted. Excluding the broker from the proxy instead trades this 403
    for a DNS failure.
    """
    if egress.mode is EgressMode.ALLOW_ALL:
        return None

    broker_port = server_port()
    lines = [
        f"http_port {EGRESS_PROXY_PORT}",
        # Log to the file the ubuntu/squid entrypoint tails to stdout;
        # writing /dev/stdout directly fails once squid drops to the
        # unprivileged proxy user, which aborts startup.
        "access_log daemon:/var/log/squid/access.log squid",
        "cache deny all",
        # A broker call blocked on a human approval sends no bytes for as long
        # as the human takes, and squid's 15-minute default would abort the
        # stream mid-decision: the shim reports "broker unreachable" while the
        # host side still runs the command once approved.
        "read_timeout 1 day",
        "# Standard CONNECT/SSL ports",
        "acl SSL_ports port 443",
        # Deduped: squid warns on a repeated port, and the conf is rendered
        # once per provisioning, so a squid still up from before a port change
        # answers every broker call with 403 until it is recreated.
        f"acl Safe_ports port {' '.join(dict.fromkeys(['80', '443', str(broker_port)]))}",
        "acl CONNECT method CONNECT",
        "http_access deny CONNECT !SSL_ports",
        "http_access deny !Safe_ports",
    ]
    if egress.mode is EgressMode.ALLOW:
        domains = sorted({egress.domain(h) for h in egress.hosts})
        for d in domains:
            # A leading-dot dstdomain matches the apex (pypi.org) and all
            # subdomains (api.pypi.org). Squid 6 fatally rejects also
            # listing the bare apex as a redundant subdomain, so emit only
            # the dotted form.
            lines.append(f"acl allowed_domains dstdomain .{d}")
        lines.append("http_access allow allowed_domains")
    lines += [
        f"acl broker dstdomain {BROKER_HOST}",
        f"acl broker_port port {broker_port}",
        "http_access allow broker broker_port",
        "http_access deny all",
    ]
    return "\n".join(lines) + "\n"


def _host_repo_bind(env: str, repo: str) -> dict[str, Any]:
    """RO mount of a host repo's gitdir at its own host path.

    Source *and* target interpolate the same env var, so the gitdir appears
    in the container exactly where clones' and quarantines' alternates lines
    say it is. The /hg-void fallback only guards direct compose invocations.
    """
    return {
        "type": "bind",
        "source": f"${{{env}:-/dev/null}}",
        "target": f"${{{env}:-/hg-void/{repo}}}",
        "read_only": True,
    }


def _quarantine_bind(env: str, repo: str) -> dict[str, Any]:
    return {
        "type": "bind",
        "source": f"${{{env}:-/dev/null}}",
        "target": quarantine_mount(repo),
        "read_only": False,
    }


def _workspace_volumes() -> list[str | dict[str, Any]]:
    """RW /app + /harness + /shared session clones and /quarantine push
    targets; RO /tools (shims+docs), package, and host repo gitdirs.

    Don't set working_dir: cwd is applied per-exec (`-w /app`), and overriding
    a container's own working_dir can break its entrypoint. The /dev/null
    fallbacks only guard direct compose invocations; the manager always
    supplies the env vars.
    """
    return [
        f"${{{WORKSPACE_ENV}:-.}}:{WORKSPACE_MOUNT}:rw",
        f"${{{HARNESS_ENV}:-/dev/null}}:{HARNESS_MOUNT}:rw",
        f"${{{SHARED_ENV}:-/dev/null}}:{SHARED_MOUNT}:rw",
        f"${{{TOOLS_ENV}:-/dev/null}}:{TOOLS_MOUNT}:ro",
        f"${{{PACKAGE_ENV}:-/dev/null}}:{PACKAGE_MOUNT}:ro",
        _host_repo_bind(HOST_REPO_APP_ENV, REPO_APP),
        _host_repo_bind(HOST_REPO_HARNESS_ENV, REPO_HARNESS),
        _host_repo_bind(HOST_REPO_SHARED_ENV, REPO_SHARED),
        _host_repo_bind(HOST_OBJECTS_APP_ENV, f"{REPO_APP}-objects"),
        _quarantine_bind(QUARANTINE_APP_ENV, REPO_APP),
        _quarantine_bind(QUARANTINE_HARNESS_ENV, REPO_HARNESS),
        _quarantine_bind(QUARANTINE_SHARED_ENV, REPO_SHARED),
        f"{GITDIR_VOLUME}:{GITDIR_MOUNT_ROOT}",
    ]


def _image_section(sandbox: ProjectSandbox, c) -> dict[str, Any]:
    """A plain registry ref on an infra container is pull-only; everything else
    compiles to a build tagged per (sandbox, container) — not the per-session
    compose project — so every session shares one image and the startup
    prebuild can warm it. Workspace containers also get REQUIRED_BUILD_STEPS."""
    if isinstance(c.image, str) and c.skip_workspace_mount:
        return {"image": c.image}
    img = Image(base=c.image) if isinstance(c.image, str) else c.image
    required = "" if c.skip_workspace_mount else REQUIRED_BUILD_STEPS
    return {
        "image": built_image_tag(sandbox.id, c.id),
        "build": _build_section(img, required),
    }


def _apply_restricted_egress(svc: dict[str, Any], sandbox: ProjectSandbox) -> None:
    proxy = f"http://{EGRESS_PROXY_SERVICE}:{EGRESS_PROXY_PORT}"
    env = svc.setdefault("environment", {})
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.setdefault(key, proxy)
    no_proxy = ",".join(["localhost", "127.0.0.1", EGRESS_PROXY_SERVICE, *sandbox.container_ids])
    env.setdefault("NO_PROXY", no_proxy)
    env.setdefault("no_proxy", no_proxy)
    svc.setdefault("networks", []).append(EGRESS_INTERNAL_NETWORK)
    svc.setdefault("depends_on", [])
    if EGRESS_PROXY_SERVICE not in svc["depends_on"]:
        svc["depends_on"].append(EGRESS_PROXY_SERVICE)


def _session_label() -> dict[str, str]:
    return {SESSION_LABEL: f"${{{SESSION_ENV}:-}}"}


def _proxy_service(sandbox: ProjectSandbox) -> dict[str, Any]:
    return {
        "image": SQUID_IMAGE,
        # Path is relative to the compose file's dir; the manager writes the
        # resolved compose beside the generated squid.conf.
        "volumes": [f"./{sandbox.id}.squid.conf:/etc/squid/squid.conf:ro"],
        "networks": [EGRESS_INTERNAL_NETWORK, EGRESS_EXTERNAL_NETWORK],
        # Squid is the only hop that reaches the harness; Desktop/OrbStack
        # inject host-gateway for ordinary containers but not reliably for a
        # compose service.
        "extra_hosts": [f"{BROKER_HOST}:host-gateway"],
        "labels": {"hypergolic.role": "proxy", **_session_label()},
    }


def _service_for(sandbox: ProjectSandbox, c, is_default: bool) -> dict[str, Any]:
    svc: dict[str, Any] = {}
    if not c.skip_workspace_mount:
        svc["volumes"] = _workspace_volumes()
    for m in c.host_mounts:
        # Long-form bind entry: never falls back to named-volume
        # interpretation and is robust to ':' in the source path.
        svc.setdefault("volumes", []).append({
            "type": "bind",
            "source": str(Path(m.source).expanduser()),
            "target": m.target,
            "read_only": m.read_only,
        })
    svc.update(_image_section(sandbox, c))
    if c.command is not None:
        svc["command"] = c.command
    if c.environment:
        svc["environment"] = dict(c.environment)
    if c.cpus is not None:
        svc["cpus"] = c.cpus
        svc.setdefault("environment", {}).setdefault("HG_CPUS", str(math.ceil(c.cpus)))
    if c.mem_limit is not None:
        svc["mem_limit"] = c.mem_limit
    if c.depends_on:
        svc["depends_on"] = list(c.depends_on)
    if c.networks:
        svc["networks"] = list(c.networks)
    if c.healthcheck:
        hc = c.healthcheck
        svc["healthcheck"] = {
            "test": ["CMD-SHELL", hc.test],
            "interval": hc.interval,
            "timeout": hc.timeout,
            "retries": hc.retries,
            "start_period": hc.start_period,
        }
    for v in sandbox.volumes:
        if c.id in v.mounts:
            svc.setdefault("volumes", []).append(f"{v.id}:{v.mounts[c.id]}")

    labels = {"hypergolic.description": c.id, **_session_label()}
    if is_default:
        labels["hypergolic.default"] = "true"
    if c.expose:
        labels["hypergolic.expose"] = ",".join(f"{p.name}={p.container}" for p in c.expose)
    svc["labels"] = labels

    if sandbox.egress.is_restricted:
        _apply_restricted_egress(svc, sandbox)
    return svc


def compile_compose(sandbox: ProjectSandbox) -> dict[str, Any]:
    """Compile to a Docker Compose dict the sandbox manager can run.

    The first container is labelled ``hypergolic.default`` so manager code
    that resolves a default service keeps working.
    """
    restricted = sandbox.egress.is_restricted
    services = {
        c.id: _service_for(sandbox, c, is_default=(i == 0))
        for i, c in enumerate(sandbox.containers)
    }

    # Under restricted egress, force every user network internal so a
    # container cannot bypass the proxy via a directly-routable network.
    networks: dict[str, Any] = {
        n.id: ({"internal": True} if (n.internal or restricted) else {})
        for n in sandbox.networks
    }
    if restricted:
        services[EGRESS_PROXY_SERVICE] = _proxy_service(sandbox)
        networks[EGRESS_INTERNAL_NETWORK] = {"internal": True}
        networks[EGRESS_EXTERNAL_NETWORK] = {}

    compose: dict[str, Any] = {"services": services}
    if networks:
        compose["networks"] = networks
    if any(not c.skip_workspace_mount for c in sandbox.containers):
        # Per-session gitdir volume: non-external, so teardown's `down -v`
        # deletes the session's repos with the sandbox (by design -- unmerged
        # work is recoverable from session history only).
        compose.setdefault("volumes", {})[GITDIR_VOLUME] = {}
    if sandbox.volumes:
        # Shared volumes get a stable global name and external: true so
        # teardown's `down -v` never removes them; the manager creates them
        # idempotently before `up` (compose errors on missing externals).
        compose.setdefault("volumes", {}).update({
            v.id: {"name": v.global_name, "external": True} if v.shared else {}
            for v in sandbox.volumes
        })
    return compose
