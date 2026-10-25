"""Browse files inside a session's running sandbox containers.

Unlike the host file browser (which walks the worktree on the local
filesystem and annotates git status), this reads files *inside* a chosen
sandbox container via ``docker compose exec``. Every location — the worktree
at ``/app``, the shared scratchpad at ``/shared``, and any user-declared
volume — is just a path inside a container, so browsing is one uniform
"exec ``ls``/``cat`` at a path" operation.

Constraints that shape this module:

- We can only rely on POSIX primitives present in essentially any image
  (``ls``, ``cat``, ``test``). No git, no ``find -printf``, no tooling we
  can't assume the user's image ships.
- The server has no filesystem handle into the container, so there is no
  efficient change-watch channel: listings are pulled on demand (lazy, one
  directory level per request) and refreshed manually from the UI.
"""

from __future__ import annotations

from pydantic import BaseModel

from hypergolic.files.language import detect_language
from hypergolic.sandbox.manager.exec import exec_in_sandbox
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.sandbox.model.constants import SANDBOX_TOOL_ID, SHARED_MOUNT, WORKSPACE_MOUNT
from hypergolic.sandbox.model.sandbox import ProjectSandbox
import posixpath
import shlex

# Guard against dumping a giant file across the exec boundary.
MAX_FILE_BYTES = 1_000_000


class SandboxRoot(BaseModel):
    """A browsable root within a container."""

    id: str  # stable key the UI sends back (e.g. "worktree", "shared", volume id)
    label: str
    path: str  # absolute path inside the container


class SandboxContainer(BaseModel):
    id: str
    roots: list[SandboxRoot]


class SandboxContainersResponse(BaseModel):
    session_id: str
    containers: list[SandboxContainer]


def list_containers(session_id: str, sandbox: ProjectSandbox | None) -> SandboxContainersResponse:
    """Enumerate browsable containers and their volume roots.

    Returns an empty list when the project opted out of a sandbox. The roots
    are derived purely from the compose model (which mounts go where), so this
    needs no running container.
    """
    if sandbox is None:
        return SandboxContainersResponse(session_id=session_id, containers=[])

    containers: list[SandboxContainer] = []
    for container in sandbox.containers:
        roots: list[SandboxRoot] = []
        if not container.skip_workspace_mount:
            roots.append(SandboxRoot(id="worktree", label="Project worktree", path=WORKSPACE_MOUNT))
            roots.append(SandboxRoot(id="shared", label="Shared scratchpad", path=SHARED_MOUNT))
        for volume in sandbox.volumes:
            mount = volume.mounts.get(container.id)
            if mount is not None:
                roots.append(SandboxRoot(id=volume.id, label=volume.id, path=mount))
        containers.append(SandboxContainer(id=container.id, roots=roots))

    return SandboxContainersResponse(session_id=session_id, containers=containers)


class SandboxNode(BaseModel):
    name: str
    path: str  # absolute path inside the container
    is_dir: bool


class SandboxTreeResponse(BaseModel):
    container: str
    root: str
    path: str  # the directory that was listed (absolute, inside container)
    nodes: list[SandboxNode]


class SandboxContentResponse(BaseModel):
    container: str
    path: str
    content: str
    language: str
    truncated: bool


def _normalize_within_root(root: str, path: str | None) -> str:
    """Resolve ``path`` to an absolute container path confined to ``root``.

    ``path`` may be absolute (already inside root) or relative to root. Reject
    anything that escapes via ``..`` so a browse request can't walk the
    container's whole filesystem.
    """

    root_norm = posixpath.normpath(root)
    if not path or path == root_norm:
        return root_norm

    candidate = path if posixpath.isabs(path) else posixpath.join(root_norm, path)
    candidate = posixpath.normpath(candidate)

    if candidate != root_norm and not candidate.startswith(root_norm + "/"):
        raise ValueError(f"Path '{path}' escapes root '{root}'")
    return candidate


def _shell_quote(value: str) -> str:
    return shlex.quote(value)


async def list_directory(
    session_id: str, container: str, root: str, path: str | None, project_root: str | None
) -> SandboxTreeResponse:
    """List a single directory level inside a container (lazy expansion).

    Uses ``ls -Ap1`` which appends ``/`` to directory names and works on both
    busybox and GNU coreutils — no reliance on ``find`` flags or git.
    """
    target = _normalize_within_root(root, path)
    quoted = _shell_quote(target)
    # -A: include dotfiles but not . / ..  -p: mark dirs with trailing /  -1: one per line.
    command = f"ls -Ap1 -- {quoted}"

    result = await exec_in_sandbox(
        session_id=session_id,
        tool_id=SANDBOX_TOOL_ID,
        command=command,
        container=container,
        project_root=project_root,
    )

    if result.returncode != 0:
        raise SandboxError(result.stderr.strip() or f"Failed to list '{target}'")

    nodes: list[SandboxNode] = []
    for line in result.stdout.splitlines():
        entry = line.rstrip("\n")
        if not entry:
            continue
        is_dir = entry.endswith("/")
        name = entry[:-1] if is_dir else entry
        if not name:
            continue
        child = target.rstrip("/") + "/" + name if target != "/" else "/" + name
        nodes.append(SandboxNode(name=name, path=child, is_dir=is_dir))

    nodes.sort(key=lambda n: (not n.is_dir, n.name.lower()))
    return SandboxTreeResponse(container=container, root=root, path=target, nodes=nodes)


async def read_file(
    session_id: str, container: str, root: str, path: str, project_root: str | None
) -> SandboxContentResponse:
    """Read a file inside a container, guarding size and binary content."""
    target = _normalize_within_root(root, path)
    quoted = _shell_quote(target)

    # Reject directories and oversized files before paying to stream content.
    # head -c keeps the transfer bounded; we flag truncation separately.
    command = (
        f"if [ -d {quoted} ]; then exit 3; fi; "
        f"head -c {MAX_FILE_BYTES + 1} -- {quoted}"
    )

    result = await exec_in_sandbox(
        session_id=session_id,
        tool_id=SANDBOX_TOOL_ID,
        command=command,
        container=container,
        project_root=project_root,
    )

    if result.returncode == 3:
        raise IsADirectoryError(target)
    if result.returncode != 0:
        raise SandboxError(result.stderr.strip() or f"Failed to read '{target}'")

    content = result.stdout
    if "\x00" in content:
        raise ValueError("Binary file")
    encoded = content.encode("utf-8", errors="replace")
    truncated = len(encoded) > MAX_FILE_BYTES
    if truncated:
        content = encoded[:MAX_FILE_BYTES].decode("utf-8", errors="ignore")

    return SandboxContentResponse(
        container=container,
        path=target,
        content=content,
        language=detect_language(target),
        truncated=truncated,
    )
