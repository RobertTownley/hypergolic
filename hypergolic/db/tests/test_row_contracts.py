from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from hypergolic.artifacts import artifact_rows
from hypergolic.db.engine import get_db
from hypergolic.db.models import DBArtifact, DBMessage, DBSessionWorkflow
from hypergolic.messages import message_rows
from hypergolic.sessions import session_rows
from hypergolic.skills import activation_rows
from hypergolic.workflows import workflow_rows
from tests.conftest import make_session


@pytest.fixture(params=[pytest.param("db", marks=pytest.mark.db), "memory"])
def backend(request):
    return request.param


async def test_session_rows(backend):
    make_session(sid="p", project_id="proj")
    make_session(sid="c1", project_id="proj", parent_id="p")
    make_session(sid="c2", project_id="proj", parent_id="p")

    assert session_rows.fetch("nope") is None
    with pytest.raises(NoResultFound):
        session_rows.fetch_one("nope")
    assert session_rows.fetch_one("p").project_id == "proj"
    assert {r.id for r in session_rows.find(parent_id="p")} == {"c1", "c2"}

    session_rows.update("c1", status="concluded", description="d")
    await session_rows.aupdate("c2", conclusion_rating=5)
    session_rows.update("nope", status="concluded")
    assert await session_rows.atransition("p", "idle", status="concluding")
    assert not await session_rows.atransition("p", "idle", status="concluded")
    assert session_rows.fetch_one("p").status == "concluding"
    c1, c2 = session_rows.fetch_one("c1"), await session_rows.afetch("c2")
    assert (c1.status, c1.description) == ("concluded", "d")
    assert c2 is not None and c2.conclusion_rating == 5

    session_rows.update("c1", resume_pending=True)
    assert [r.id for r in session_rows.claim_resume_flags()] == ["c1"]
    assert session_rows.claim_resume_flags() == []
    assert session_rows.fetch_one("c1").resume_pending is False

    make_session(sid="g", project_id="proj", parent_id="c1")
    session_rows.delete("p")
    assert [session_rows.fetch(s) for s in ("p", "c1", "c2", "g")] == [None] * 4


def test_message_rows_sequence_and_truncation(backend):
    make_session(sid="s", project_id="proj")
    make_session(sid="other", project_id="proj")
    message_rows.insert(
        DBMessage(session_id="s", role="user", content=[{"type": "text", "text": "a"}]),
        DBMessage(session_id="s", role="assistant", content=[{"type": "text", "text": "b"}]),
        DBMessage(session_id="other", role="user", content=[]),
    )
    message_rows.insert(DBMessage(session_id="s", role="user", content=[], sequence=7))
    message_rows.insert(DBMessage(session_id="s", role="user", content=[]))

    rows = message_rows.for_session("s")
    assert [r.sequence for r in rows] == [1, 2, 7, 8]
    assert [r.role for r in rows[:2]] == ["user", "assistant"]
    assert not any(r.truncated for r in rows)

    last, last_reply = message_rows.last("s"), message_rows.last("s", role="assistant")
    assert (last and last.sequence, last_reply and last_reply.sequence) == (8, 2)

    first, second, *_ = rows
    message_rows.splice("s", [second.id], DBMessage(session_id="s", role="user", content=[], sequence=7))
    assert [(r.sequence, r.truncated) for r in message_rows.for_session("s")] == [
        (1, False), (2, True), (7, False), (8, False), (9, False)]
    assert message_rows.last("s", role="assistant") is None

    message_rows.truncate("s")
    assert all(r.truncated for r in message_rows.for_session("s"))
    assert not any(r.truncated for r in message_rows.for_session("other"))


async def test_workflow_rows(backend):
    make_session(sid="s", project_id="proj")
    assert workflow_rows.active("s") is None
    await workflow_rows.start("s", "wf", "a")
    await workflow_rows.move("s", "b")
    assert workflow_rows.active("s") == ("wf", "b")
    await workflow_rows.end("s")
    assert workflow_rows.active("s") is None
    await workflow_rows.start("s", "wf2", "x")
    assert workflow_rows.active("s") == ("wf2", "x")


async def test_artifact_rows(backend):
    make_session(sid="s", project_id="proj")
    for i, outcome in enumerate(["ok", "fail", "ok"]):
        await artifact_rows.add(DBArtifact(
            session_id="s", workflow_id="wf", state_id=f"st{i}", outcome=outcome,
            artifact_id=f"a{i}", content={"i": i},
            created_at=datetime(2025, 1, 1, 0, 0, i, tzinfo=timezone.utc),
        ))

    assert [r.artifact_id for r in artifact_rows.find(session_id="s")] == ["a0", "a1", "a2"]
    assert [r.artifact_id for r in artifact_rows.find(outcome="ok", newest_first=True)] == ["a2", "a0"]
    assert [r.artifact_id for r in artifact_rows.find(newest_first=True, offset=1, limit=1)] == ["a1"]
    first = artifact_rows.find(artifact_id="a0")[0]
    got = artifact_rows.get(first.id)
    assert got is not None and got.content == {"i": 0}
    assert artifact_rows.get("nope") is None


async def test_activation_rows(backend):
    make_session(sid="s", project_id="proj")
    for skill in ["git", "css", "git"]:
        await activation_rows.record("s", skill)
    assert activation_rows.skill_ids("s") == ["git", "css"]
    assert activation_rows.skill_ids("other") == []


@pytest.mark.db
async def test_workflow_end_keeps_the_row_soft_deleted():
    make_session(sid="s", project_id="proj")
    await workflow_rows.start("s", "wf", "a")
    await workflow_rows.end("s")
    with get_db() as db:
        [row] = db.scalars(select(DBSessionWorkflow).where(DBSessionWorkflow.session_id == "s")).all()
        assert row.deleted_at is not None
