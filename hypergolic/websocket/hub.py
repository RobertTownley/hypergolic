"""Process-global WebSocket fan-out.

Turns are process-owned tasks (see ``turn_manager``); connections merely
attach to observe them. Events fan out to every live connection best-effort —
a dead socket is dropped, never raised, and a disconnect never touches a
running turn.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class JsonSender(Protocol):
    async def send_json(self, data: dict[str, Any], /) -> None: ...


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: list[JsonSender] = []

    def attach(self, ws: JsonSender) -> None:
        if ws not in self._connections:
            self._connections.append(ws)

    def detach(self, ws: JsonSender) -> None:
        try:
            self._connections.remove(ws)
        except ValueError:
            pass

    async def send(self, payload: dict[str, Any]) -> None:
        for ws in list(self._connections):
            try:
                await ws.send_json(payload)
            except Exception:
                logger.debug("Dropping dead WebSocket from hub", exc_info=True)
                self.detach(ws)


_hub = ConnectionHub()


def get_hub() -> ConnectionHub:
    return _hub
