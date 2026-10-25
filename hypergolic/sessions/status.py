import asyncio


from hypergolic.sessions import session_rows
from hypergolic.enums import SessionStatus
from hypergolic.messages.types import BroadcastEvent, BroadcastFn


TERMINAL_STATUSES = frozenset(
    {SessionStatus.CONCLUDING, SessionStatus.CONCLUDED, SessionStatus.INTERRUPTED}
)


async def session_ended(session_id: str) -> bool:
    row = await session_rows.afetch(session_id)
    if row is None:
        return False
    return row.concluded_at is not None or SessionStatus(row.status) in TERMINAL_STATUSES


def get_session_status(session_id: str) -> SessionStatus:
    return SessionStatus(session_rows.fetch_one(session_id).status)


async def finalize_turn(session_id: str, broadcast: BroadcastFn) -> None:
    current = await asyncio.to_thread(get_session_status, session_id)
    if current not in TERMINAL_STATUSES:
        await set_session_status_and_broadcast(session_id, SessionStatus.IDLE, broadcast)


def set_session_status(session_id: str, status: SessionStatus) -> None:
    session_rows.update(session_id, status=status)


async def set_session_status_and_broadcast(
    session_id: str,
    status: SessionStatus,
    broadcast: BroadcastFn,
) -> None:
    await asyncio.to_thread(set_session_status, session_id, status)
    await broadcast(
        BroadcastEvent(
            type="session_status_change",
            role="system",
            content=[{"status": status.value}],
            session_id=session_id,
        )
    )
