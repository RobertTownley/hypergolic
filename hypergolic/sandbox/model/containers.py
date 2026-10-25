from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from hypergolic.sandbox.model.constants import (
    HARNESS_MOUNT,
    PACKAGE_MOUNT,
    SHARED_MOUNT,
    TOOLS_MOUNT,
    WORKSPACE_MOUNT,
)

_MEM_LIMIT = re.compile(r"^[1-9][0-9]*[bkmg]?$", re.IGNORECASE)


class Image(BaseModel):
    """A container image authored in Python.

    ``base`` becomes the Dockerfile's ``FROM``; ``steps`` are verbatim
    Dockerfile instructions (multiline entries fine). Hypergolic owns the
    frame around the steps: required tooling is inserted after them while
    still root, and ``user`` (when set) is emitted last — so a non-root final
    user can never break the agent toolchain contract.

    Steps may not declare build stages (``FROM ... AS x``): a new stage would
    become the final image and silently escape that frame. Lift files from
    other images with ``COPY --from=<image-ref>`` instead.

    ``context`` is only needed when steps COPY local files; it anchors those
    paths (absolute, or relative to the generated compose dir).
    ``additional_contexts`` maps names to host paths for
    ``COPY --from=<name>`` sources that live outside ``context`` (e.g. the
    project checkout itself, so builds read current files with no snapshot
    drift).
    """

    base: str
    steps: list[str] = Field(default_factory=list)
    user: str | None = None
    context: str | None = None
    additional_contexts: dict[str, str] = Field(default_factory=dict)
    args: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> "Image":
        # First line of each entry only: interior lines of a multiline entry
        # can legitimately start with 'from' (heredoc Python, etc.).
        for step in self.steps:
            first = step.lstrip().split("\n", 1)[0]
            if first.lower().startswith("from "):
                raise ValueError(
                    f"Image steps cannot declare build stages ('{first.strip()}'): the new "
                    "stage would become the final image and bypass required steps and "
                    "user. Use COPY --from=<image-ref> to lift files from other images."
                )
        return self


class Port(BaseModel):
    """A container port to expose on a dynamically-allocated host port.

    No host port is authored; the manager allocates a free one per session
    (see P2). ``name`` is how the endpoint appears in the session context.
    """

    container: int
    name: str


class Healthcheck(BaseModel):
    test: str
    interval: str = "10s"
    timeout: str = "5s"
    retries: int = 3
    start_period: str = "0s"


class Volume(BaseModel):
    """A named volume and the per-container paths it mounts at.

    By default the volume is compose-project-scoped: each session gets a
    fresh one and teardown (``down -v``) removes it. Set ``shared=True`` for
    a stable global volume named ``hypergolic-shared-<id>`` that persists
    across sessions and projects — e.g. package-manager caches (uv, pnpm)
    so later sessions install dependencies from cache instead of the network.
    """

    id: str
    mounts: dict[str, str] = Field(default_factory=dict)
    shared: bool = False

    @property
    def global_name(self) -> str:
        return f"hypergolic-shared-{self.id}"


class HostMount(BaseModel):
    """A host directory bind-mounted into a container.

    Read-only by default: exposing host data to the agent should opt into
    writability explicitly. ``source`` is ``~``-expanded at compile time
    (relative to the host user running the server).
    """

    source: str
    target: str
    read_only: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "HostMount":
        if not Path(self.source).expanduser().is_absolute():
            raise ValueError(
                f"HostMount source must be an absolute or ~-relative host path "
                f"(got '{self.source}')"
            )
        if not self.target.startswith("/"):
            raise ValueError(f"HostMount target must be absolute (got '{self.target}')")
        reserved = {WORKSPACE_MOUNT, HARNESS_MOUNT, SHARED_MOUNT, TOOLS_MOUNT, PACKAGE_MOUNT}
        if self.target.rstrip("/") in reserved:
            raise ValueError(f"HostMount target '{self.target}' collides with a built-in mount")
        return self


class Network(BaseModel):
    id: str
    internal: bool = False


class Container(BaseModel):
    id: str
    image: "str | Image"
    """A registry ref (pull-only for infra containers; workspace containers
    build FROM it so required steps apply) or an authored :class:`Image`."""
    command: list[str] | str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    expose: list[Port] = Field(default_factory=list)
    healthcheck: Healthcheck | None = None
    networks: list[str] = Field(default_factory=list)
    host_mounts: list[HostMount] = Field(default_factory=list)
    skip_workspace_mount: bool = False
    """Opt out of the /app git-dir mount (e.g. stock infra images like postgres)."""
    cpus: float | None = Field(default=None, gt=0)
    """CPU quota in cores (compose ``cpus``). The container still sees every
    host core in ``nproc``, so the quota is also exported as ``HG_CPUS``
    (rounded up) for sizing test workers and build jobs."""
    mem_limit: str | None = None
    """Hard memory cap in compose form (``512m``, ``2g``). The kernel OOM-kills
    past it, so size JVMs (``-Xmx``) and test runs to fit inside."""

    @model_validator(mode="after")
    def _validate(self) -> "Container":
        if self.mem_limit is not None and not _MEM_LIMIT.match(self.mem_limit):
            raise ValueError(
                f"Container '{self.id}' mem_limit must look like '512m' or '2g' "
                f"(got '{self.mem_limit}')"
            )
        targets = [m.target.rstrip("/") for m in self.host_mounts]
        dupes = {t for t in targets if targets.count(t) > 1}
        if dupes:
            raise ValueError(
                f"Container '{self.id}' has duplicate host mount targets: {sorted(dupes)}"
            )
        return self
