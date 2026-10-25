"""Everything the harness injects into a container exec, and the registry that
authorizes what comes back.

Three values have to reach a sandbox process for it to invoke a host command:
where the broker listens, which session it belongs to, and which exec it is part
of. They are assembled in exactly one place so a call site cannot inject a
different ``PATH`` than the one ``/tools/bin`` was materialized for, or reach a
port the server isn't on.

``EXEC_REGISTRY`` is the authorization boundary for the broker. The session
token says *which session*; a live registry entry says *a real tool call is in
flight right now*. A process that outlives its exec holds a stale ``exec_id``
and is refused — which forecloses the dormant-hostile-code path rather than
merely making it visible.

The registry is a plain dict, sound only because the harness is a single
process (uvicorn in a daemon thread, same interpreter as the broker route). A
refactor to multiple workers must move it to shared state or execs registered
by one worker will be rejected by another.
"""

from __future__ import annotations

import secrets
import threading
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from time import time
from typing import Iterator

from opentelemetry import context as otel_context

from hypergolic.config.settings import settings

#: Where the shims live inside the container. Must precede the image's own
#: directories: the startup collision check assumes ``/tools/bin`` wins.
TOOLS_BIN = "/tools/bin"

#: Prepends the shim directory to whatever ``PATH`` the image already sets, then
#: runs the agent's command line as ``$1``.
#:
#: Injecting ``-e PATH=...`` instead would *replace* the image's own PATH, losing
#: what a project's base image puts there (cargo, node, ruby prefixes), and no rc
#: file can extend it because execs run ``sh -c`` non-interactively. Passing the
#: command as an argument rather than interpolating it means no quoting layer
#: between the agent (or a host-side repair such as ``tool/heredoc.py``) and
#: the shell. ``eval`` rather than a nested ``sh -c`` so
#: nothing depends on finding ``sh`` again under the PATH we just changed.
PATH_PRELUDE = f'PATH="{TOOLS_BIN}:$PATH"; export PATH; eval "$1"'

#: Stateful prelude (agent-facing ``cmd`` only; internal plumbing stays
#: stateless so agent state can't leak into it). Snapshot via ``export -p`` in
#: a subshell that unsets the per-exec injections — line-based filtering would
#: corrupt multiline values — landing by atomic rename so a concurrent exec
#: never sources a half-written file.
_RESTORE_CWD = '[ -r "$HG_STATE/.hg_cwd" ] && cd "$(cat "$HG_STATE/.hg_cwd")"; '

def _persist_prelude(restore_cwd: bool) -> str:
    return (
        'HG_STATE="${HG_STATE_DIR:-/tmp}"; '
        '[ -r "$HG_STATE/.hg_env" ] && . "$HG_STATE/.hg_env"; '
        f'case ":$PATH:" in *":{TOOLS_BIN}:"*) ;; *) PATH="{TOOLS_BIN}:$PATH";; esac; export PATH; '
        + (_RESTORE_CWD if restore_cwd else '')
        + 'eval "$1"; hg_rc=$?; '
        '{ (unset HG_BROKER HG_TOKEN HG_EXEC_ID HG_STATE HG_STATE_DIR PWD OLDPWD; export -p) > "$HG_STATE/.hg_env.$$" '
        '&& mv "$HG_STATE/.hg_env.$$" "$HG_STATE/.hg_env"; '
        + ('pwd > "$HG_STATE/.hg_cwd"; ' if restore_cwd else '')
        + '} 2>/dev/null; exit $hg_rc'
    )

#: Containers reach the host's loopback listener through this name; OrbStack and
#: Docker Desktop both proxy it, so the server never binds a routable address.
BROKER_HOST = "host.docker.internal"

_lock = threading.Lock()


@dataclass(frozen=True)
class ExecRecord:
    """What one in-flight exec was for.

    ``command`` is the full string the agent asked for — the approval card reads
    it from here rather than accepting it from the shim, which only ever sees
    the fragment the sandbox shell forked it with.
    """

    session_id: str
    command: str
    container: str | None
    sandbox_id: str | None
    started_at: float
    #: The trace context current at registration (the ``sandbox.exec`` span).
    #: Broker invocations parent their spans on it; the shim carries nothing.
    trace_context: otel_context.Context | None = None


EXEC_REGISTRY: dict[str, ExecRecord] = {}

#: session_id -> token, and its inverse. Minted when a session first needs an
#: exec, discarded on teardown; never rotated in between.
_SESSION_TOKENS: dict[str, str] = {}
_TOKEN_SESSIONS: dict[str, str] = {}

#: exec_id -> count of broker invocations currently in flight under it. Any
#: nonzero count suspends the exec's timeout: the auto-approved-but-slow case is
#: the common one, so pausing only for pending approvals would leave it unhandled.
_IN_FLIGHT: Counter[str] = Counter()


def server_port() -> int:
    return settings.HYPERGOLIC_PORT


def broker_address() -> str:
    return f"{BROKER_HOST}:{server_port()}"


def session_token(session_id: str) -> str:
    """The session's broker token, minted on first use."""
    with _lock:
        token = _SESSION_TOKENS.get(session_id)
        if token is None:
            token = secrets.token_urlsafe(32)
            _SESSION_TOKENS[session_id] = token
            _TOKEN_SESSIONS[token] = session_id
        return token


def resolve_token(token: str) -> str | None:
    """The session a bearer token identifies, or ``None`` if it identifies none.

    The loopback port is reachable by every container on the machine, so this is
    the only thing standing between one session's sandbox and another's
    capability. Compared in constant time against each candidate.
    """
    if not token:
        return None
    with _lock:
        for candidate, session_id in _TOKEN_SESSIONS.items():
            if secrets.compare_digest(candidate, token):
                return session_id
    return None


def discard_session_token(session_id: str) -> None:
    with _lock:
        token = _SESSION_TOKENS.pop(session_id, None)
        if token is not None:
            _TOKEN_SESSIONS.pop(token, None)


def register_exec(
    session_id: str,
    command: str,
    container: str | None = None,
    sandbox_id: str | None = None,
) -> str:
    """Mint a correlation id for one exec and record what it was for."""
    exec_id = secrets.token_urlsafe(16)
    with _lock:
        EXEC_REGISTRY[exec_id] = ExecRecord(
            session_id=session_id,
            command=command,
            container=container,
            sandbox_id=sandbox_id,
            started_at=time(),
            trace_context=otel_context.get_current(),
        )
    return exec_id


def release_exec(exec_id: str) -> None:
    with _lock:
        EXEC_REGISTRY.pop(exec_id, None)
        _IN_FLIGHT.pop(exec_id, None)


def lookup_exec(exec_id: str | None) -> ExecRecord | None:
    if not exec_id:
        return None
    with _lock:
        return EXEC_REGISTRY.get(exec_id)


@contextmanager
def timeout_suspended(exec_id: str | None) -> Iterator[None]:
    """Stop the exec's countdown for the lifetime of one broker invocation.

    A human reading a diff may take many minutes and there is no defensible
    number to pick, so the pause is indefinite. Liveness comes from the
    connection instead: if the host side drops the request the shim sees a closed
    socket and exits nonzero.
    """
    if not exec_id:
        yield
        return
    with _lock:
        _IN_FLIGHT[exec_id] += 1
    try:
        yield
    finally:
        with _lock:
            _IN_FLIGHT[exec_id] -= 1
            if _IN_FLIGHT[exec_id] <= 0:
                del _IN_FLIGHT[exec_id]


def is_timeout_suspended(exec_id: str | None) -> bool:
    if not exec_id:
        return False
    with _lock:
        return _IN_FLIGHT.get(exec_id, 0) > 0


def exec_env(session_id: str, exec_id: str) -> list[str]:
    """Compose ``-e`` flags for one exec. The single place this is decided."""
    return [
        "-e", f"HG_BROKER={broker_address()}",
        "-e", f"HG_TOKEN={session_token(session_id)}",
        "-e", f"HG_EXEC_ID={exec_id}",
    ]


def exec_argv(command: str, *, persist_state: bool = False, restore_cwd: bool = True) -> list[str]:
    """What the container actually runs: the agent's line, with shims on PATH.

    ``persist_state`` selects the stateful prelude (see above). ``restore_cwd``
    is ignored without it; pass False when an explicit workdir was requested:
    such an exec neither restores nor saves cwd — `-w` is a one-shot override,
    not a relocation — but env still persists.
    """
    prelude = _persist_prelude(restore_cwd) if persist_state else PATH_PRELUDE
    return ["sh", "-c", prelude, "hypergolic", command]
