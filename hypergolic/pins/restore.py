from __future__ import annotations

from typing import TYPE_CHECKING


from hypergolic.sessions import session_rows
from hypergolic.harness.app.state import get_app
from hypergolic.pins.app_overrides import overridden_app
from hypergolic.pins.runtime import pin_app

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App


def load_app_overrides(session_id: str) -> dict[str, object]:
    row = session_rows.fetch(session_id)
    return (row.app_overrides if row else None) or {}


def restore_overridden_app(session_id: str) -> "App | None":
    overrides = load_app_overrides(session_id)
    if not overrides:
        return None
    app = overridden_app(get_app(), overrides)
    pin_app(session_id, app)
    return app
