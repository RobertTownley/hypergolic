from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App

_current_app: App | None = None

#: Context-scoped override: lets a pinned harness App drive a turn
#: without touching the process-wide App every other session resolves.
_context_app: ContextVar["App | None"] = ContextVar("hypergolic_context_app", default=None)


def set_app(app: App) -> None:
    global _current_app
    _current_app = app


def get_app() -> App:
    app = _context_app.get()
    if app is not None:
        return app
    if _current_app is None:
        raise RuntimeError("No App has been initialized. Call set_app() first.")
    return _current_app


def live_app() -> App | None:
    """The process-wide App, ignoring any context override; None before set_app."""
    return _current_app


@contextmanager
def app_context(app: App) -> Iterator[App]:
    token = _context_app.set(app)
    try:
        yield app
    finally:
        _context_app.reset(token)
