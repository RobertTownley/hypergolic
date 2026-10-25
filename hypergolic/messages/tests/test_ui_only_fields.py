from __future__ import annotations


from typing import Any, cast

from anthropic.types import MessageParam

from hypergolic.messages import message_rows
from hypergolic.messages.persistence import load_session_messages, persist_messages
from tests.conftest import make_project, make_session


META = {"workflow_id": "wf-1", "workflow_state_name": "Draft"}


async def test_meta_is_stored_but_stripped_from_replayed_history():
    make_project()
    sid = make_session(sid="meta-session")
    messages = cast(
        list[MessageParam],
        [
            {"role": "user", "content": [{"type": "text", "text": "go"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu-1", "name": "workflow_transition_x", "input": {}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu-1",
                        "content": [{"type": "text", "text": "Transitioned."}],
                        "is_error": False,
                        "meta": META,
                    }
                ],
            },
        ],
    )
    await persist_messages(session_id=sid, messages=messages)

    rows = message_rows.for_session(sid)
    assert cast(dict, rows[2].content[0])["meta"] == META

    replayed = cast(list[dict[str, Any]], load_session_messages(sid)[2]["content"])
    assert "meta" not in replayed[0]
    assert replayed[0]["content"] == [{"type": "text", "text": "Transitioned."}]
