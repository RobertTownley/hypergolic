import threading
from collections.abc import Callable
from contextlib import contextmanager
from typing import cast, Iterator, TypeVar

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import create_engine, Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from hypergolic.config.settings import settings

_engine: Engine | None = None
_async_engine: AsyncEngine | None = None
# run_db() makes first-use reachable from worker threads concurrently;
# guard lazy init so racing callers can't construct (and leak) two engines.
_engine_lock = threading.Lock()
_async_engine_lock = threading.Lock()

_T = TypeVar("_T")


def _async_url(url: str) -> str:
    """Map a sync SQLAlchemy URL to its asyncpg counterpart.

    Postgres URLs written for the sync driver (``postgresql://`` /
    ``postgresql+psycopg://``) are rewritten to ``postgresql+asyncpg://``
    so the runtime awaits real nonblocking I/O while Alembic and other sync
    consumers keep the original psycopg URL.
    """
    scheme, sep, rest = url.partition("://")
    dialect = scheme.split("+", 1)[0]
    return f"{dialect}+asyncpg{sep}{rest}"


_ASYNC_DRIVERS = frozenset({"asyncpg", "psycopg_async"})


def sync_url(url: str) -> str:
    """Pin sync URLs to an explicit installed driver.

    A bare ``postgresql://`` URL resolves to psycopg2, which is not
    installed; psycopg (v3) is. An explicitly async URL (what someone
    configuring an async app is likely to write) has no sync DBAPI at all.
    Either way, rewrite the scheme so Alembic and every synchronous consumer
    bind to the driver actually present.
    """
    scheme, sep, rest = url.partition("://")
    dialect, _, driver = scheme.partition("+")
    if driver and driver not in _ASYNC_DRIVERS:
        return url
    return f"{dialect}+psycopg{sep}{rest}"


def _create_engine() -> Engine:
    engine = create_engine(sync_url(settings.HYPERGOLIC_DATABASE_URL))
    SQLAlchemyInstrumentor().instrument(engine=engine)
    return engine


def _create_async_engine() -> AsyncEngine:
    # NullPool: asyncpg opens connections cheaply; the server-side pool is
    # the real bound.
    engine = create_async_engine(
        _async_url(settings.HYPERGOLIC_DATABASE_URL), poolclass=NullPool
    )
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = _create_engine()
    return _engine


def get_async_engine() -> AsyncEngine:
    global _async_engine
    if _async_engine is None:
        with _async_engine_lock:
            if _async_engine is None:
                _async_engine = _create_async_engine()
    return _async_engine


@contextmanager
def get_db() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as session:
        with session.begin():
            yield session


def _run_sync_in_session(session: Session, fn: Callable[[Session], _T]) -> _T:
    with session.begin():
        return fn(session)


async def run_db(fn: Callable[[Session], _T]) -> _T:
    """Run *fn* against a DB session, off the event loop.

    *fn* is written against the synchronous ``Session`` API — query
    execution *and* attribute loads on returned rows must all happen inside
    it, since the session is committed and closed before the result returns
    (``expire_on_commit=False`` keeps already-loaded attributes usable).

    ``run_sync`` drives the sync-style *fn* inside a greenlet; when the ORM
    performs I/O it awaits asyncpg on the event loop itself — no thread hop,
    and concurrency is bounded by the connection pool rather than the thread
    pool.
    """
    async with AsyncSession(get_async_engine(), expire_on_commit=False) as session:
        return cast(_T, await session.run_sync(_run_sync_in_session, fn))
