import asyncio

import pytest

from hypergolic.commands.broker.heartbeat import PING, with_heartbeat


async def _collect(source, interval):
    return [c async for c in with_heartbeat(source, interval)]


async def test_pings_while_the_source_is_silent():
    async def slow():
        await asyncio.sleep(0.05)
        yield b"done"

    out = await _collect(slow(), 0.01)
    assert out[-1] == b"done"
    assert PING in out[:-1]


async def test_passes_chunks_through_without_pings_when_busy():
    async def fast():
        yield b"a"
        yield b"b"

    assert await _collect(fast(), 1) == [b"a", b"b"]


async def test_source_errors_propagate():
    async def boom():
        yield b"a"
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await _collect(boom(), 1)
