
from hypergolic.sessions import session_rows


def get_session_description(session_id: str) -> str | None:
    return session_rows.fetch_one(session_id).description


def save_description(session_id: str, description: str) -> None:
    session_rows.update(session_id, description=description)
