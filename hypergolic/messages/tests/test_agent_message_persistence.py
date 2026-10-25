from hypergolic.messages import message_rows
from hypergolic.messages.persistence import persist_agent_message
from tests._factories import build_assistant_message
from tests.conftest import make_project, make_session


async def test_same_provider_reply_persists_in_each_session():
    make_project()
    sessions = [make_session(sid="dup-a"), make_session(sid="dup-b")]
    reply = build_assistant_message(mid="msg_bdrk_cached")

    ids = [await persist_agent_message(sid, reply) for sid in sessions]

    rows = {r.id: r for sid in sessions for r in message_rows.for_session(sid)}
    assert ids[0] != ids[1]
    assert [rows[i].session_id for i in ids] == sessions
    assert {rows[i].provider_message_id for i in ids} == {"msg_bdrk_cached"}
