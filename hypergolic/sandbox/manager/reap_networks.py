"""Networks outlive their containers when Docker loses a stack behind our back
(VM restart, external prune); the container-driven reaper can't see them, and
each holds one of the daemon's scarce address-pool subnets."""

import logging

from hypergolic.sandbox.manager import docker
from hypergolic.sandbox.manager.lifecycle import _list_compose_projects
from hypergolic.sandbox.manager.provisioning import COMPOSE_PROJECT_PREFIX
from hypergolic.sandbox.manager.types import SandboxError

logger = logging.getLogger(__name__)

_PROJECT_LABEL = "com.docker.compose.project"


async def _compose_networks() -> list[tuple[str, str]] | None:
    result = await docker._run_docker(
        "network", "ls", "--filter", f"label={_PROJECT_LABEL}",
        "--format", f'{{{{.Name}}}}\t{{{{.Label "{_PROJECT_LABEL}"}}}}',
        timeout=15,
    )
    if result.returncode != 0:
        return None
    pairs = (line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line)
    return [(name, project) for name, project in pairs if project.startswith(COMPOSE_PROJECT_PREFIX)]


async def reap_orphaned_networks(protected: set[str]) -> int:
    """Remove our networks whose project has no containers at all. ``protected``
    covers stacks mid-`up` (networks exist before containers); `network rm`
    refusing an attached network is the backstop."""
    try:
        networks = await _compose_networks()
        occupied = await _list_compose_projects()
    except (SandboxError, OSError):
        logger.warning("Could not list networks to reap", exc_info=True)
        return 0
    if networks is None or occupied is None:
        return 0
    orphans = sorted(n for n, p in networks if p not in occupied and p not in protected)
    reaped = 0
    for name in orphans:
        try:
            result = await docker._run_docker("network", "rm", name, timeout=30)
        except (SandboxError, OSError):
            logger.warning("Failed to reap network %s", name, exc_info=True)
            continue
        if result.returncode == 0:
            reaped += 1
        else:
            logger.warning("Reap of network %s reported: %s", name, result.stderr.strip())
    if reaped:
        logger.info("Reaped %d orphaned sandbox network(s)", reaped)
    return reaped
