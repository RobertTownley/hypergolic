"""The CLI broker must bind an ephemeral port and repoint the shim address."""
import httpx2

from hypergolic.cli.broker_server import start_broker
from hypergolic.config.settings import settings


async def test_start_broker_binds_and_updates_settings():
    original = settings.HYPERGOLIC_PORT
    try:
        broker = await start_broker()
        try:
            assert broker.port != 0
            assert settings.HYPERGOLIC_PORT == broker.port
            # Route is live; an unauthenticated invoke is rejected, not unreachable.
            async with httpx2.AsyncClient() as client:
                resp = await client.post(
                    f"http://127.0.0.1:{broker.port}/broker/invoke",
                    json={"command": "x"},
                )
            assert resp.status_code == 401
        finally:
            await broker.stop()
        assert broker.task.done()
    finally:
        settings.HYPERGOLIC_PORT = original
