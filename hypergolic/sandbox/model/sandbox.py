from __future__ import annotations


from pydantic import BaseModel, Field, model_validator

from hypergolic.sandbox.model.constants import PACKAGE_MOUNT
from hypergolic.sandbox.model.containers import Container, Image, Network, Volume
from hypergolic.sandbox.model.egress import Egress

class ProjectSandbox(BaseModel):
    id: str
    containers: list[Container]
    networks: list[Network] = Field(default_factory=list)
    volumes: list[Volume] = Field(default_factory=list)
    egress: Egress = Field(default_factory=Egress.DenyAll)
    command_timeout: int | None = Field(default=None, gt=0)

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _validate(self) -> "ProjectSandbox":
        if not self.containers:
            raise ValueError(f"Sandbox '{self.id}' must declare at least one container")

        ids = [c.id for c in self.containers]
        dupes = {cid for cid in ids if ids.count(cid) > 1}
        if dupes:
            raise ValueError(f"Sandbox '{self.id}' has duplicate container ids: {sorted(dupes)}")

        known = set(ids)
        for c in self.containers:
            for dep in c.depends_on:
                if dep not in known:
                    raise ValueError(
                        f"Container '{c.id}' depends_on unknown container '{dep}'"
                    )

        net_ids = {n.id for n in self.networks}
        for c in self.containers:
            for net in c.networks:
                if net not in net_ids:
                    raise ValueError(
                        f"Container '{c.id}' references unknown network '{net}'"
                    )

        vol_ids = [v.id for v in self.volumes]
        vol_dupes = {vid for vid in vol_ids if vol_ids.count(vid) > 1}
        if vol_dupes:
            raise ValueError(f"Sandbox '{self.id}' has duplicate volume ids: {sorted(vol_dupes)}")
        for v in self.volumes:
            for cid in v.mounts:
                if cid not in known:
                    raise ValueError(
                        f"Volume '{v.id}' mounts into unknown container '{cid}'"
                    )

        port_names: list[str] = [p.name for c in self.containers for p in c.expose]
        name_dupes = {n for n in port_names if port_names.count(n) > 1}
        if name_dupes:
            raise ValueError(
                f"Sandbox '{self.id}' has duplicate exposed port names: {sorted(name_dupes)}"
            )

        return self

    @property
    def container_ids(self) -> list[str]:
        return [c.id for c in self.containers]

    def squid_conf_filename(self) -> str:
        return f"{self.id}.squid.conf"


DEFAULT_SANDBOX_ID = "default"

#: Pinned so the required-steps layer never runs an installer script and every
#: install resolves the same uv build.
UV_IMAGE = "ghcr.io/astral-sh/uv:0.11.13"

#: Pinned like UV_IMAGE, and matched to the interpreter Hypergolic itself
#: runs on: every workspace image carries the identical uv-managed build,
#: fetched once at image build (cached layer), never at session time.
PYTHON_VERSION = "3.14.2"

#: Pinned like UV_IMAGE. The PyPI wheel ships prebuilt ast-grep/sg binaries.
AST_GREP_VERSION = "0.45.1"

#: Inserted into every workspace container's Dockerfile at compose-compile
#: time (see :func:`hypergolic.sandbox.compose.compile_compose`), after the
#: authored steps and before any ``Image.user`` — i.e. still as root. Every
#: session prompt tells the agent to run `uv run /shared/main.py`, so uv is
#: part of the contract no matter what base the project authored. Guarded
#: (and a bind mount rather than a COPY) so images that manage uv themselves
#: — e.g. a wrapper script at /usr/local/bin/uv — are left untouched.
#: The fallback warning (rather than failing the layer) covers a USER snuck
#: into verbatim steps: a missing uv beats a sandbox that no longer builds.
#:
#: The interpreter step is deliberately not guarded: tool shims hard-depend on
#: ``/usr/local/bin/hg-python`` (see :mod:`hypergolic.commands.shim`), so an
#: image that can't provide it must fail at build — visibly, once — rather
#: than mid-session as a broken tool call on every invocation. ``hg-python``
#: is a dedicated name so it never shadows, nor depends on, whatever python
#: the project's own image or venv provides. UV_PYTHON_INSTALL_DIR persists
#: to runtime, so ``uv run``/``uv sync`` in-session resolve the same managed
#: interpreter with no download. Mirror-only networks set
#: UV_PYTHON_INSTALL_MIRROR in authored steps, which render before these.
#:
#: ast-grep: the role prompt mandates it, so every workspace image needs it;
#: warns rather than fails like the uv step.
#:
#: edit: the role prompt's file-edit command. A two-line wrapper rather than a
#: copy, so :mod:`hypergolic.sandbox.edit` runs from the read-only package
#: mount and tracks the installed package without an image rebuild.
REQUIRED_BUILD_STEPS = (
    # Sandbox-owned repos need real git in every workspace container.
    "RUN command -v git >/dev/null || "
    "{ apt-get update && apt-get install -y --no-install-recommends git ca-certificates; } || "
    "apk add --no-cache git || "
    "echo 'hypergolic: WARNING: could not install git; install it in your Dockerfile' >&2\n"
    "RUN command -v jq >/dev/null || "
    "{ apt-get update && apt-get install -y --no-install-recommends jq; } || "
    "apk add --no-cache jq || "
    "echo 'hypergolic: WARNING: could not install jq; install it in your Dockerfile' >&2\n"
    f"RUN --mount=from={UV_IMAGE},source=/,target=/hg-uv "
    "command -v uv >/dev/null || "
    "{ mkdir -p /usr/local/bin && cp /hg-uv/uv /hg-uv/uvx /usr/local/bin/; } 2>/dev/null || "
    "echo 'hypergolic: WARNING: could not install uv (non-root final USER?);"
    " install uv in your Dockerfile' >&2\n"
    "ENV UV_PYTHON_INSTALL_DIR=/opt/hypergolic/python\n"
    f"RUN uv python install {PYTHON_VERSION} && "
    f"ln -sf \"$(uv python find --managed-python {PYTHON_VERSION})\" "
    "/usr/local/bin/hg-python\n"
    "RUN UV_TOOL_BIN_DIR=/usr/local/bin UV_TOOL_DIR=/opt/hypergolic/uv-tools "
    f"uv tool install --python /usr/local/bin/hg-python ast-grep-cli=={AST_GREP_VERSION} || "
    "echo 'hypergolic: WARNING: could not install ast-grep' >&2\n"
    "RUN { echo '#!/bin/sh'; "
    f"echo 'exec /usr/local/bin/hg-python {PACKAGE_MOUNT}/sandbox/edit.py \"$@\"'; "
    "} > /usr/local/bin/edit && chmod +x /usr/local/bin/edit\n"
)

# uv comes from REQUIRED_BUILD_STEPS like every other workspace container.
_DEFAULT_IMAGE_STEPS = [
    "ENV DEBIAN_FRONTEND=noninteractive",
    """RUN apt-get update && apt-get install -y --no-install-recommends \\
      python3 python3-pip python3-venv \\
      git curl wget ca-certificates \\
      build-essential make \\
      jq \\
      sudo \\
    && ln -sf /usr/bin/python3 /usr/local/bin/python \\
    && rm -rf /var/lib/apt/lists/*""",
    """RUN echo 'ALL ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/hypergolic \\
    && chmod 0440 /etc/sudoers.d/hypergolic""",
]


def default_sandbox() -> "ProjectSandbox":
    """The sandbox a project gets when it never calls ``configure_sandbox``.

    A single Ubuntu dev container with common tooling and ``Egress.DenyAll`` —
    the agent runs shell commands in a contained environment with no outbound
    network until the project opts into egress via its own ``ProjectSandbox``.

    Returns a fresh instance per call so callers can never mutate a shared
    singleton out from under other unconfigured projects.
    """
    return ProjectSandbox(
        id=DEFAULT_SANDBOX_ID,
        containers=[
            Container(
                id="dev",
                image=Image(base="ubuntu:26.04", steps=_DEFAULT_IMAGE_STEPS),
                command=["sleep", "infinity"],
            )
        ],
        egress=Egress.DenyAll(),
    )
