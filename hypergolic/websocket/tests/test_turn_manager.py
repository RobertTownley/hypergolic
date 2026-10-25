import asyncio

import pytest

from hypergolic.websocket.turn_manager import TurnManager


def test_init():
    tm = TurnManager()
    assert tm.session_tasks == {}
    assert tm.session_cancel_events == {}
    assert tm.pending_approvals == {}
    assert tm.approval_payloads == {}


def test_singleton():
    from hypergolic.websocket.turn_manager import get_turn_manager
    assert get_turn_manager() is get_turn_manager()


async def test_start_turn():
    tm = TurnManager()
    ran = False

    async def coro(cancel_event: asyncio.Event) -> None:
        nonlocal ran
        ran = True

    task = tm.start_turn("s1", coro)
    await task
    assert ran
    assert "s1" not in tm.session_tasks


@pytest.mark.timeout(2)
async def test_cancel_existing_turn(monkeypatch):
    monkeypatch.setattr("hypergolic.websocket.turn_manager.CANCEL_GRACE", 0.01)
    tm = TurnManager()

    async def long_coro(cancel_event: asyncio.Event) -> None:
        await asyncio.sleep(10)

    tm.start_turn("s1", long_coro)
    await tm.cancel_existing_turn("s1")
    assert "s1" not in tm.session_tasks or tm.session_tasks["s1"].done()


async def test_cancel_nonexistent_turn():
    tm = TurnManager()
    await tm.cancel_existing_turn("nonexistent")


@pytest.mark.timeout(2)
async def test_cancel_approvals_for_session(monkeypatch):
    monkeypatch.setattr("hypergolic.websocket.turn_manager.CANCEL_GRACE", 0.01)
    tm = TurnManager()
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    tm.pending_approvals["tu-1"] = ("s1", fut)

    async def long_coro(cancel_event: asyncio.Event) -> None:
        await asyncio.sleep(10)

    tm.start_turn("s1", long_coro)
    await tm.cancel_existing_turn("s1")
    assert fut.cancelled()
    assert "tu-1" not in tm.pending_approvals


async def test_start_turn_cleanup_callback():
    """Done callback only cleans up if the task matches."""
    tm = TurnManager()

    async def coro1(cancel_event: asyncio.Event) -> None:
        pass

    async def coro2(cancel_event: asyncio.Event) -> None:
        await asyncio.sleep(10)

    task1 = tm.start_turn("s1", coro1)
    task2 = tm.start_turn("s1", coro2)
    await task1
    assert tm.session_tasks.get("s1") is task2
    task2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task2


async def test_cancel_done_task():
    """Cancelling a task that already finished is a no-op."""
    tm = TurnManager()

    async def fast_coro(cancel_event: asyncio.Event) -> None:
        pass

    task = tm.start_turn("s1", fast_coro)
    await task
    await tm.cancel_existing_turn("s1")


@pytest.mark.timeout(2)
async def test_cancel_turn_cooperative_exit():
    """Task that respects cancel_event exits quickly."""
    tm = TurnManager()

    async def cooperative_coro(cancel_event: asyncio.Event) -> None:
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)

    tm.start_turn("s1", cooperative_coro)
    await tm.cancel_existing_turn("s1")
