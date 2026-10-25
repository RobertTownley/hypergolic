import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from hypergolic.commands.broker.auth import InvokeRequest, authorize
from hypergolic.commands.broker.heartbeat import with_heartbeat
from hypergolic.commands.broker.stream import stream
from hypergolic.commands.registry import session_commands
from hypergolic.sandbox.exec_env import timeout_suspended
from hypergolic.sessions.operations import load_session

router = APIRouter(prefix="/broker", tags=["broker"])

@router.post("/invoke")
async def invoke(request: Request) -> StreamingResponse:
    body = InvokeRequest.model_validate(await request.json())
    session_id, record = authorize(request, body)


    session = await asyncio.to_thread(load_session, session_id)
    commands = await asyncio.to_thread(session_commands, session)
    command = commands.get(body.command)
    if command is None or not command.invocable:
        raise HTTPException(
            status_code=404,
            detail=f"no command '{body.command}' in this session",
        )

    async def frames() -> AsyncIterator[bytes]:
        # The countdown on the exec that spawned this shim stops for as long as
        # the invocation lives: a human reading a diff, an OAuth round trip, or
        # simply a slow host command all outlast the default timeout.
        with timeout_suspended(body.exec_id):
            async for chunk in with_heartbeat(stream(session, record, command, body)):
                yield chunk

    return StreamingResponse(frames(), media_type="application/x-ndjson")
