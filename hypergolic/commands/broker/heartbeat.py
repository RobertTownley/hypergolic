import asyncio
from typing import AsyncIterator

HEARTBEAT_SECONDS = 15.0
PING = b'{"type": "ping"}\n'


async def with_heartbeat(
    source: AsyncIterator[bytes], interval: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for chunk in source:
                queue.put_nowait(chunk)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), interval)
            except TimeoutError:
                yield PING
                continue
            if chunk is None:
                break
            yield chunk
        await task
    finally:
        task.cancel()
