"""In-process command broker for `hypergolic run`.

Sandbox shims dial ``host.docker.internal:<HYPERGOLIC_PORT>`` with a bearer
token minted in whichever process created the session. Tokens live in process
memory (``exec_env._TOKEN_SESSIONS``), so a CLI-created sandbox can only ever
authenticate against a broker served *by the CLI process* — the long-running
server, if one is listening on the default port, rejects it with 401.

Hence: serve the broker route here on an ephemeral port and point
``settings.HYPERGOLIC_PORT`` at it before any container env is injected
(``exec_env.broker_address()`` reads the setting per exec). The broker runs
as a task on the caller's event loop, keeping the CLI single-loop: shim-
invoked tools execute on the same loop as the turn, so loop-bound state
(provider client pools, ready-events) never crosses loops.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Generator
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI

from hypergolic.commands.broker import router
from hypergolic.config.settings import settings
from hypergolic.logging import uvicorn_log_config


class _NoSignalServer(uvicorn.Server):
    """Ctrl-C belongs to the CLI turn, not the broker."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        yield


@dataclass
class RunningBroker:
    server: uvicorn.Server
    task: asyncio.Task
    port: int

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task


async def start_broker(timeout: float = 10.0) -> RunningBroker:
    """Serve /broker on an ephemeral loopback port on the running loop."""
    api = FastAPI()
    api.include_router(router)
    server = _NoSignalServer(
        uvicorn.Config(
            api,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            log_config=uvicorn_log_config(),
        )
    )
    task = asyncio.create_task(server.serve())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not server.started:
        if task.done():
            raise RuntimeError("CLI broker failed to start") from task.exception()
        if loop.time() > deadline:
            task.cancel()
            raise RuntimeError("CLI broker failed to start within timeout")
        await asyncio.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    settings.HYPERGOLIC_PORT = port
    return RunningBroker(server=server, task=task, port=port)
