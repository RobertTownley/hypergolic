import logging

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from hypergolic.sandbox.exec_env import ExecRecord, lookup_exec, resolve_token

logger = logging.getLogger(__name__)


class InvokeRequest(BaseModel):
    command: str
    argv: list[str] = Field(default_factory=list)
    cwd: str | None = None
    exec_id: str | None = None
    #: Text for `@-` argv tokens to become. Quote-heavy values (DQL, nested
    #: JSON) travel as a heredoc instead of running the shell-escaping gauntlet.
    stdin: str | None = None


def bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def authorize(request: Request, body: InvokeRequest) -> tuple[str, ExecRecord]:
    """Establish the session, then that an authorized window is open.

    The token says *which session*; ``EXEC_REGISTRY`` membership says *that a real
    tool call is in flight right now*. Both are required, and the registry entry
    \u2014 not the request \u2014 fixes what the caller may reach, so a live key cannot be
    borrowed to target a container its own exec was not aimed at.

    The deliberate consequence: a process that outlives its exec (a dev server
    backgrounded three turns ago, a dormant compromised dependency) holds a stale
    id and is refused.
    """
    session_id = resolve_token(bearer(request))
    if session_id is None:
        client = request.client.host if request.client else "unknown"
        logger.warning("Broker request with invalid or absent token from %s", client)
        raise HTTPException(status_code=401, detail="invalid broker token")

    record = lookup_exec(body.exec_id)
    if record is None:
        logger.warning(
            "Broker request for session %s with unknown or stale exec_id", session_id
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "no tool call is in flight for this exec. Commands are reachable "
                "only from a process the harness started."
            ),
        )
    if record.session_id != session_id:
        logger.warning(
            "Cross-session broker attempt: token session %s used exec_id owned by %s",
            session_id, record.session_id,
        )
        raise HTTPException(status_code=403, detail="exec_id belongs to another session")
    return session_id, record

