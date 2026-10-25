import asyncio
from unittest.mock import AsyncMock


def make_deps():
    notify = AsyncMock()
    broadcast = AsyncMock()
    approval_callback = AsyncMock()
    cancel_event = asyncio.Event()
    return notify, broadcast, approval_callback, cancel_event
