enabled_servers_by_session: dict[str, set[str]] = {}


def get_enabled_servers(session_id: str) -> set[str]:
    return enabled_servers_by_session.get(session_id, set()).copy()


def set_enabled_servers(session_id: str, servers: set[str]) -> None:
    enabled_servers_by_session[session_id] = servers


def sessions_using(server_name: str, exclude: str | None = None) -> set[str]:
    """Which other sessions still want this server connected.

    Deactivation is per session but the connection is process-wide, so the last
    session to let go is the one that may close it.
    """
    return {
        session_id
        for session_id, servers in enabled_servers_by_session.items()
        if server_name in servers and session_id != exclude
    }


def clear_enabled_servers(session_id: str) -> None:
    """Remove the session's enabled-server set, so it no longer counts as a
    user of those servers in :func:`sessions_using`.

    Runs when a session concludes or is deleted. It does not close any
    connection.

    Left behind, its entry counts as a user forever, so no later deactivate can
    close the shared connection and reactivating hands back the same one.
    """
    enabled_servers_by_session.pop(session_id, None)
