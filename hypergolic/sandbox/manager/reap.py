"""Orphan reaping: compose projects and per-session internals no live
session claims. Runs at startup and, debounced, whenever a session is created
— teardown misses (killed app, timed-out `down`) are collected here."""

import asyncio
import logging
import shutil
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update

from hypergolic.config.settings import settings
from hypergolic.db.engine import get_db, run_db
from hypergolic.db.models import DBSandbox, DBSession
from hypergolic.enums import SessionStatus
from hypergolic.sandbox.manager import docker
from hypergolic.sandbox.manager.lifecycle import _list_compose_projects, remove_gitdir_volume
from hypergolic.sandbox.manager.provisioning import (
    _cleanup_resolved_config,
    _resolved_config_path,
)
from hypergolic.sandbox.manager.reap_networks import reap_orphaned_networks
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.telemetry.tracing import root_span

logger = logging.getLogger(__name__)


def _has_authoritative_db() -> bool:
    """Can this process's DB say which sandboxes are live?

    A throwaway DB (tests set HYPERGOLIC_SANDBOX_REAP=false) sees no sessions
    and no sandbox rows, which would make every managed container on the host
    look orphaned. Nothing is torn down on that evidence.
    """
    return settings.HYPERGOLIC_SANDBOX_REAP

#: Set on every container Hypergolic compiles (see compose.compile_compose);
#: distinguishes our compose projects from the user's own stacks.
MANAGED_LABEL = "hypergolic.description"

#: A concluded session's sandbox row whose status changed this recently is left
#: alone — a readiness probe or eval can still be driving an already-wrapped-up
#: session, and reaping under it would kill a live container.
REAP_GRACE = timedelta(minutes=10)

#: Floor on how often a session-triggered reap actually runs.
_REAP_MIN_INTERVAL_SECONDS = 60.0

_reap_state_lock = threading.Lock()
_reap_in_flight = False
_last_reap_at = 0.0

#: The server's event loop, bound at startup. Session creation runs on FastAPI's
#: sync threadpool, which has no loop of its own to schedule the reap onto.
_server_loop: asyncio.AbstractEventLoop | None = None


def bind_server_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Register (or clear) the loop background sandbox work is scheduled onto."""
    global _server_loop
    _server_loop = loop


async def _managed_compose_projects() -> set[str]:
    """Compose projects with Hypergolic-managed containers, running or not."""
    projects = await _list_compose_projects(label=MANAGED_LABEL)
    if projects is None:
        raise SandboxError("docker ps failed")
    return projects


#: Statuses of a session that ended without a `concluded_at` stamp: a dispatched
#: child swept by startup recovery or by its parent's interrupt.
_ENDED_STATUSES = (SessionStatus.CONCLUDED.value, SessionStatus.INTERRUPTED.value)


async def _protected_compose_projects() -> set[str]:
    """Projects protected while their session is still live or their row was
    touched inside :data:`REAP_GRACE`. A project with no sandbox row at all
    (deleted session) is protected by neither — exactly the leak the reaper
    collects. Scoped by nothing but this DB: two Hypergolic servers sharing a
    Docker daemon would each see the other's stacks as orphans.

    "Live" means no `concluded_at` and not an ended status — not merely
    `status != CONCLUDED`. A failed dispatch child ends as ERROR (with
    concluded_at stamped) and a child whose parent died ends INTERRUPTED;
    keying on CONCLUDED alone protected those forever.
    """
    cutoff = datetime.now(UTC) - REAP_GRACE

    def _query(db) -> list[str]:
        return list(
            db.execute(
                select(DBSandbox.compose_project)
                .join(DBSession, DBSession.id == DBSandbox.session_id)
                .where(
                    or_(
                        and_(
                            DBSession.concluded_at.is_(None),
                            DBSession.status.not_in(_ENDED_STATUSES),
                        ),
                        DBSandbox.updated_at >= cutoff,
                    )
                )
            ).scalars().all()
        )

    return {p for p in await run_db(_query) if p}


async def reap_orphaned_compose_projects() -> int:
    """`down` every managed compose project no live session claims; returns a
    count. Docker is the source of truth: row-driven cleanup misses the worst
    orphans, whose rows were marked stopped by a timed-out `down`, or deleted
    with their session."""
    if not _has_authoritative_db():
        return 0

    try:
        managed = await _managed_compose_projects()
    except (SandboxError, OSError):
        logger.warning("Could not list compose projects to reap", exc_info=True)
        return 0

    orphans = sorted(managed - await _protected_compose_projects())
    if not orphans:
        return 0

    logger.info("Reaping %d orphaned sandbox project(s): %s", len(orphans), orphans)
    reaped = 0
    for project in orphans:
        try:
            result = await docker._run_docker(
                "compose", "-p", project,
                "down", "--remove-orphans", "-v", "--timeout", "5",
                timeout=120,
            )
        except (SandboxError, OSError):
            logger.warning("Failed to reap sandbox project %s", project, exc_info=True)
            continue
        if result.returncode != 0:
            logger.warning(
                "Reap of sandbox project %s reported: %s", project, result.stderr.strip()
            )
            continue
        reaped += 1
        await remove_gitdir_volume(project)
        await _retire_rows(project)
    return reaped


async def _recently_touched_projects() -> set[str]:
    cutoff = datetime.now(UTC) - REAP_GRACE

    def _query(db) -> list[str]:
        return list(db.execute(
            select(DBSandbox.compose_project).where(
                or_(DBSandbox.updated_at >= cutoff, DBSandbox.status == "pending")
            )
        ).scalars().all())

    return {p for p in await run_db(_query) if p}


async def reap_orphans() -> None:
    """Stacks first: their `down` frees networks the second pass would redo."""
    await reap_orphaned_compose_projects()
    if _has_authoritative_db():
        await reap_orphaned_networks(await _recently_touched_projects())


async def _retire_rows(compose_project: str) -> None:
    """Mark a reaped project's rows stopped and drop its resolved compose file."""
    def _retire(db) -> list[str]:
        rows = db.execute(
            select(DBSandbox).where(DBSandbox.compose_project == compose_project)
        ).scalars().all()
        paths = [r.config_path for r in rows if r.config_path]
        db.execute(
            update(DBSandbox)
            .where(DBSandbox.compose_project == compose_project)
            .values(status="stopped")
        )
        return paths

    for config_path in await run_db(_retire):
        _cleanup_resolved_config(
            str(_resolved_config_path(config_path, compose_project))
        )


def reap_orphaned_session_dirs() -> int:
    """Delete per-session internals (quarantines, tools, clone mounts) whose
    session row is gone or concluded — conclusion removes these; this backstop
    handles the dirs it never got to."""
    from hypergolic.config.settings import INTERNALS_DIR, sessions_internals_root

    with get_db() as db:
        live = set(db.execute(
            select(DBSession.id).where(DBSession.status != SessionStatus.CONCLUDED)
        ).scalars().all())
    reaped = 0
    for root in (INTERNALS_DIR / "quarantine", sessions_internals_root()):
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and child.name not in live:
                shutil.rmtree(child, ignore_errors=True)
                reaped += 1
    return reaped


def schedule_reap() -> None:
    """Kick a reap from synchronous code (session creation) without blocking it.

    Debounced and single-flight, so a burst of dispatched sessions triggers one
    reap rather than one each. A no-op when no server loop is bound (CLI, tests).
    """
    global _reap_in_flight
    loop = _server_loop
    if loop is None or loop.is_closed():
        return
    with _reap_state_lock:
        if _reap_in_flight or time.monotonic() - _last_reap_at < _REAP_MIN_INTERVAL_SECONDS:
            return
        _reap_in_flight = True
    try:
        asyncio.run_coroutine_threadsafe(_reap_once(), loop)
    except RuntimeError:
        # The loop closed between the check and the call (shutdown).
        with _reap_state_lock:
            _reap_in_flight = False


async def _reap_once() -> None:
    global _reap_in_flight, _last_reap_at
    try:
        with root_span("sandbox.reap"):
            await reap_orphans()
    except Exception:
        logger.warning("Background sandbox reap failed", exc_info=True)
    finally:
        with _reap_state_lock:
            _reap_in_flight = False
            _last_reap_at = time.monotonic()

