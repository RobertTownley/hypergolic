"""Automatic AWS SSO session recovery for Bedrock-backed tiers.

botocore refreshes SSO access tokens on its own (starting 15 minutes before
expiry), but a refresh is rejected outright once the IAM Identity Center
session hits its org-configured maximum duration. From that point every
Bedrock request fails with ``TokenRetrievalError`` until a human runs
``aws sso login`` — an interactive browser round-trip no client-side token
logic can substitute for. This module automates that recovery: a pre-flight
probe that exercises botocore's own token path, and an ``aws sso login``
runner for when the session is truly dead.

botocore is imported lazily throughout, against repo convention: importing it
captures ssl.SSLContext at import time (botocore.httpsession deliberately
keeps the unpatched class), so it must stay downstream of ssl_bootstrap's
truststore injection or TLS verification silently bypasses the OS trust store.
"""

from __future__ import annotations

import asyncio
import logging
import time

from hypergolic.config.models import SsoConfig
from hypergolic.harness.app.state import get_app

logger = logging.getLogger(__name__)

# One interactive login attempt per profile per window, so a retry loop (or
# parallel sessions hitting the same expiry) can't spawn a stack of browser
# tabs. A successful login yields an access token good for an hour or more.
# Failed attempts back off exponentially and stop at
# App(sso=SsoConfig(max_login_attempts=...)); a successful login or probe re-arms.
LOGIN_THROTTLE_SECONDS = 60.0
_login_failures: dict[str | None, int] = {}
_next_login_allowed: dict[str | None, float] = {}

# The pre-flight probe re-reads AWS config + token cache from disk; once per
# window per profile is plenty.
PROBE_THROTTLE_SECONDS = 30.0
_last_probe: dict[str | None, float] = {}


def _sso() -> SsoConfig:
    try:
        return get_app().sso
    except RuntimeError:
        return SsoConfig()


def reset_throttles() -> None:
    """Clear throttle state (tests)."""
    _login_failures.clear()
    _next_login_allowed.clear()
    _last_probe.clear()


def login_attempts_exhausted(profile: str | None) -> bool:
    return _login_failures.get(profile, 0) >= _sso().max_login_attempts


def _record_login_failure(profile: str | None) -> None:
    failures = _login_failures.get(profile, 0) + 1
    _login_failures[profile] = failures
    _next_login_allowed[profile] = (
        time.monotonic() + LOGIN_THROTTLE_SECONDS * 2**failures
    )


def sso_auth_errors() -> tuple[type[Exception], ...]:
    """Exception types that mean the SSO session is expired or unusable."""
    from botocore.exceptions import (
        SSOTokenLoadError,
        TokenRetrievalError,
        UnauthorizedSSOTokenError,
    )

    return (TokenRetrievalError, SSOTokenLoadError, UnauthorizedSSOTokenError)


def _probe_token(profile: str | None) -> None:
    """Force botocore's own load-and-refresh of *profile*'s SSO token.

    Raises one of ``sso_auth_errors()`` when the token is expired and
    unrefreshable. No-ops for profiles without an ``sso-session`` block
    (those surface through the reactive path instead) — and for
    fresh tokens this is a pure cache-file read, no network.
    """

    import botocore.session
    from botocore.tokens import SSOTokenProvider

    session = botocore.session.Session(profile=profile)
    provider = SSOTokenProvider(session, profile_name=profile)
    token = provider.load_token()
    if token is not None:
        token.get_frozen_token()


async def attempt_sso_login(profile: str | None) -> bool:
    """Run ``aws sso login`` for *profile*; True when it exits cleanly.

    Interactive: opens the system browser for the SSO round-trip. Gated by
    ``App(sso=SsoConfig(auto_login=...))`` and throttled per profile.
    """
    if not _sso().auto_login:
        return False
    if login_attempts_exhausted(profile):
        logger.error(
            "Not attempting aws sso login for %r: %d consecutive failures; "
            "run it manually",
            profile,
            _login_failures[profile],
        )
        return False
    now = time.monotonic()
    allowed = _next_login_allowed.get(profile)
    if allowed is not None and now < allowed:
        logger.info(
            "Skipping aws sso login for %r: backing off %.0fs more",
            profile,
            allowed - now,
        )
        return False
    _next_login_allowed[profile] = now + LOGIN_THROTTLE_SECONDS

    cmd = ["aws", "sso", "login"]
    if profile:
        cmd += ["--profile", profile]
    logger.warning("AWS SSO session expired; running: %s", " ".join(cmd))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        logger.error("aws CLI not found; cannot recover the SSO session automatically")
        _record_login_failure(profile)
        return False
    try:
        output, _ = await asyncio.wait_for(
            proc.communicate(), timeout=_sso().login_timeout
        )
    except TimeoutError:
        proc.kill()
        logger.error(
            "aws sso login timed out after %ss (browser approval not completed?)",
            _sso().login_timeout,
        )
        _record_login_failure(profile)
        return False
    if proc.returncode != 0:
        logger.error(
            "aws sso login failed (exit %s): %s",
            proc.returncode,
            output.decode(errors="replace").strip()[-500:],
        )
        _record_login_failure(profile)
        return False
    logger.info("aws sso login succeeded for profile %r", profile)
    _login_failures.pop(profile, None)
    return True


async def ensure_sso_session(profile: str | None) -> bool:
    """Pre-flight: if the SSO token is expired and unrefreshable, log in now.

    Returns True when a login was performed (callers should rebuild cached
    clients so stale botocore token objects are dropped). Never raises — a
    failed probe leaves recovery to the reactive handler on the real request.
    """
    errors = sso_auth_errors()
    if not errors:
        return False
    now = time.monotonic()
    last = _last_probe.get(profile)
    if last is not None and now - last < PROBE_THROTTLE_SECONDS:
        return False
    _last_probe[profile] = now
    try:
        await asyncio.to_thread(_probe_token, profile)
        _login_failures.pop(profile, None)
        _next_login_allowed.pop(profile, None)
    except errors:
        return await attempt_sso_login(profile)
    except Exception as exc:
        logger.debug("SSO pre-flight probe failed for %r: %s", profile, exc)
    return False


def actionable_sso_error(profile: str | None) -> RuntimeError:
    target = f" --profile {profile}" if profile else ""
    detail = (
        f"automatic recovery gave up after {_login_failures.get(profile, 0)} failed "
        "login attempts"
        if login_attempts_exhausted(profile)
        else "automatic recovery failed"
    )
    return RuntimeError(
        f"AWS SSO session expired and {detail}. "
        f"Run `aws sso login{target}` in a terminal, then retry."
    )
