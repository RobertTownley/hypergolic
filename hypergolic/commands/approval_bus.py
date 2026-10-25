"""Reaching a session's human from outside its tool loop.

Approvals normally flow inside a tool call: the engine holds the callback and
awaits it. A broker invocation arrives on an HTTP request instead, mid-way
through an exec the engine is already blocked on, so it needs the same callback
from a different direction.

The window is exactly one turn. Outside it there is no human to ask, which is the
same position a child session is in, and the caller treats a missing entry the
same way: the approval cannot be granted, so the invocation is denied rather than
left to hang.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypergolic.messages.types import BroadcastFn
from hypergolic.tools.approval import ApprovalCallback


@dataclass(frozen=True)
class ApprovalChannel:
    callback: ApprovalCallback
    broadcast: BroadcastFn


_CHANNELS: dict[str, ApprovalChannel] = {}


def register(session_id: str, callback: ApprovalCallback, broadcast: BroadcastFn) -> None:
    _CHANNELS[session_id] = ApprovalChannel(callback=callback, broadcast=broadcast)


def unregister(session_id: str) -> None:
    _CHANNELS.pop(session_id, None)


def channel(session_id: str) -> ApprovalChannel | None:
    return _CHANNELS.get(session_id)
