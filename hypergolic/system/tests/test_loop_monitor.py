import asyncio
import logging
import time


from hypergolic.system.loop_monitor import start_loop_lag_monitor


async def test_quiet_loop_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger="hypergolic.system.loop_monitor"):
        task = start_loop_lag_monitor(interval=0.01, threshold=1.0)
        await asyncio.sleep(0.05)
        task.cancel()
    assert not caplog.records


async def test_stalled_loop_logs_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="hypergolic.system.loop_monitor"):
        task = start_loop_lag_monitor(interval=0.01, threshold=0.05)
        await asyncio.sleep(0.02)
        time.sleep(0.15)
        await asyncio.sleep(0.02)
        task.cancel()
    assert any("Event loop stalled" in r.message for r in caplog.records)


def _block_loop():
    time.sleep(0.15)


async def test_stall_warning_names_blocking_call(caplog):
    with caplog.at_level(logging.WARNING, logger="hypergolic.system.loop_monitor"):
        task = start_loop_lag_monitor(interval=0.01, threshold=0.05)
        await asyncio.sleep(0.02)
        _block_loop()
        await asyncio.sleep(0.02)
        task.cancel()
    messages = [r.getMessage() for r in caplog.records]
    assert any("test_loop_monitor.py" in m and "_block_loop" in m for m in messages)
    assert all("\n" not in m for m in messages)
