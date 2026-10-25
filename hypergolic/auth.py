import secrets
import threading

_lock = threading.Lock()
_bootstrap_token: str = ""
_session_token: str = ""
_readonly_token: str = ""
_readonly_session_id: str = ""


def init_bootstrap_token() -> str:
    global _bootstrap_token
    _bootstrap_token = secrets.token_urlsafe(32)
    return _bootstrap_token


def redeem_bootstrap_token(value: str) -> str | None:
    """Validate and consume the one-time bootstrap token.

    Returns the session token on success, None on failure.
    The bootstrap token is destroyed regardless of outcome.
    """
    global _bootstrap_token, _session_token
    with _lock:
        if not _bootstrap_token or not value:
            return None
        valid = secrets.compare_digest(value, _bootstrap_token)
        _bootstrap_token = ""
        if not valid:
            return None
        _session_token = secrets.token_urlsafe(32)
        return _session_token


def get_session_token() -> str:
    return _session_token


def verify_token(value: str) -> bool:
    if not _session_token:
        return False
    return secrets.compare_digest(value, _session_token)


def mint_readonly_token(session_id: str) -> str:
    """Mint (or replace) the read-only UI token, scoped to one session.

    Grants GET/HEAD on /api and spectator websocket access for that session's
    data only — never approvals, turns, or other sessions'
    content. Re-minting invalidates the previous one.
    """
    global _readonly_token, _readonly_session_id
    with _lock:
        _readonly_token = secrets.token_urlsafe(32)
        _readonly_session_id = session_id
        return _readonly_token


def readonly_session(value: str) -> str | None:
    """The session a readonly token is scoped to, or None if it is invalid."""
    with _lock:
        token, session_id = _readonly_token, _readonly_session_id
    if not token or not value:
        return None
    if not secrets.compare_digest(value, token):
        return None
    return session_id
