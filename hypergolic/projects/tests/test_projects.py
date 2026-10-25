from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from hypergolic.projects.operations import latest_session_times, list_all_projects, project_name
from tests.conftest import make_project, make_session

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _names(activity: dict[str, datetime]) -> list[str]:
    with patch("hypergolic.projects.operations.latest_session_times", return_value=activity):
        return [p.name for p in list_all_projects()]


@pytest.mark.parametrize("activity, expected", [
    ({}, ["Alpha", "Bravo", "Charlie"]),
    ({"p-b": T0}, ["Bravo", "Alpha", "Charlie"]),
    ({"p-a": T0, "p-b": T0 + timedelta(hours=1), "p-c": T0 + timedelta(hours=2)}, ["Charlie", "Bravo", "Alpha"]),
    ({"p-c": T0, "p-a": T0}, ["Alpha", "Charlie", "Bravo"]),
])
def test_list_all_projects_orders_active_by_recency_then_by_name(activity, expected):
    for pid, name in [("p-c", "Charlie"), ("p-a", "Alpha"), ("p-b", "Bravo")]:
        make_project(pid, name, f"/tmp/{pid}")
    assert _names(activity) == expected


@pytest.mark.db
def test_latest_session_times_is_each_projects_newest_session():
    make_session("p-a", "s-1", created_at=T0)
    make_session("p-a", "s-2", created_at=T0 + timedelta(hours=1))
    make_session("p-b", "s-3", created_at=T0)
    assert latest_session_times() == {"p-a": T0 + timedelta(hours=1), "p-b": T0}


def test_project_name_resolves_registered_or_falls_back_to_id():
    make_project("p-named", "Pretty Name", "/tmp/named")
    assert project_name("p-named") == "Pretty Name"
    assert project_name("unregistered-id") == "unregistered-id"


@patch("hypergolic.projects.operations.latest_session_times", return_value={"p-b": T0})
def test_list_projects_endpoint(_, api_client):
    assert api_client.get("/api/projects").json() == []
    make_project("p-a", "Alpha", "/tmp/alpha")
    make_project("p-b", "Beta", "/tmp/beta")
    data = api_client.get("/api/projects").json()
    assert [(p["name"], p["last_session_at"] is not None) for p in data] == [("Beta", True), ("Alpha", False)]


def test_project_branches_not_found(api_client):
    resp = api_client.get("/api/projects/nonexistent/branches")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
