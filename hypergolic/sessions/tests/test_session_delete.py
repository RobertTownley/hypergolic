from hypergolic.sessions import session_rows
from tests.conftest import make_project, make_session


def test_delete_session_removes_its_subtree_only(api_client):
    make_project()
    make_session(sid="root")
    make_session(sid="mid", parent_id="root")
    make_session(sid="leaf", parent_id="mid")
    make_session(sid="sibling", parent_id="root")
    assert api_client.delete("/api/sessions/mid").status_code == 200
    assert [s for s in ("root", "mid", "leaf", "sibling") if session_rows.fetch(s)] == ["root", "sibling"]


def test_delete_session_nonexistent(api_client):
    assert api_client.delete("/api/sessions/does-not-exist").status_code == 200
