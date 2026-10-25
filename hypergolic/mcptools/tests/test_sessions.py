"""Enablement is per session; the connection behind it is process-wide."""

import pytest

from hypergolic.mcptools import sessions


@pytest.fixture(autouse=True)
def _empty_registry():
    sessions.enabled_servers_by_session.clear()
    yield
    sessions.enabled_servers_by_session.clear()


def test_enabled_servers_round_trip():
    sessions.set_enabled_servers("s1", {"analytics"})
    assert sessions.get_enabled_servers("s1") == {"analytics"}
    assert sessions.get_enabled_servers("unknown") == set()


def test_enabled_servers_are_copied_so_callers_cannot_mutate_the_registry():
    sessions.set_enabled_servers("s1", {"analytics"})
    sessions.get_enabled_servers("s1").add("wiki")
    assert sessions.get_enabled_servers("s1") == {"analytics"}


def test_sessions_using_reports_the_other_holders_of_a_server():
    sessions.set_enabled_servers("s1", {"analytics", "wiki"})
    sessions.set_enabled_servers("s2", {"analytics"})

    assert sessions.sessions_using("analytics") == {"s1", "s2"}
    assert sessions.sessions_using("analytics", exclude="s1") == {"s2"}
    assert sessions.sessions_using("wiki", exclude="s1") == set()


def test_clearing_a_session_releases_its_servers():
    """An ended session that still counted as a user kept a dead connection
    open: deactivate could never close it, so reactivating reused it."""
    sessions.set_enabled_servers("ended", {"gateway"})
    sessions.set_enabled_servers("live", {"wiki"})

    sessions.clear_enabled_servers("ended")
    sessions.clear_enabled_servers("never-seen")

    assert sessions.sessions_using("gateway") == set()
    assert sessions.get_enabled_servers("live") == {"wiki"}
