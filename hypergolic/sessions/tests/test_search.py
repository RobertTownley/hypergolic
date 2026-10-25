from datetime import datetime, timedelta, timezone

import pytest

from hypergolic.sessions.search import extract_text
from tests.conftest import make_message, make_project, make_session

NOW = datetime.now(timezone.utc)


def _session(sid: str, *messages: tuple[str, str], project_id: str = "proj-1", hours_ago: int = 0) -> None:
    make_session(project_id, sid, updated_at=NOW - timedelta(hours=hours_ago))
    for role, text in messages:
        make_message(sid, role, text)


def _search(api_client, **body) -> list[dict]:
    resp = api_client.post("/api/sessions/search", json=body)
    assert resp.status_code == 200
    return resp.json()["matches"]


@pytest.mark.db
def test_search_matches_each_session_once_newest_first(api_client):
    make_project("proj-1", "TestProject", "/tmp/test")
    _session("s-old", ("user", "target"), hours_ago=2)
    _session("s-new", ("assistant", "target " + "x" * 300), ("user", "first ask"), ("user", "target again"))
    _session("s-mid", ("assistant", "only assistant target"), hours_ago=1)
    _session("s-miss", ("user", "nothing here"))

    matches = _search(api_client, query="target")
    assert [m["session_id"] for m in matches] == ["s-new", "s-mid", "s-old"]
    new, mid, _ = matches
    assert (new["project_name"], new["model_tier"], new["message_count"]) == ("TestProject", "Medium", 3)
    assert (new["match_role"], len(new["match_text"]), new["first_message"]) == ("assistant", 200, "first ask")
    assert mid["first_message"] is None
    assert _search(api_client, query="zzzznotfound") == []


@pytest.mark.db
def test_search_filters_by_project_and_caps_results(api_client):
    make_project("p1", "Proj1", "/tmp/p1")
    make_project("p2", "Proj2", "/tmp/p2")
    for i in range(3):
        _session(f"a{i}", ("user", "common keyword"), project_id="p1")
    _session("b", ("user", "common keyword"), project_id="p2")

    assert [m["session_id"] for m in _search(api_client, query="common", project_id="p2")] == ["b"]
    assert len(_search(api_client, query="common", max_results=2)) == 2


def test_extract_text_reads_text_blocks_and_plain_strings():
    content = [{"type": "text", "text": "a"}, "b", {"type": "tool_use", "name": "cmd"}]
    assert extract_text(content) == "a\nb"
