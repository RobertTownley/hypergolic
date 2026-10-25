from __future__ import annotations


import logging
from typing import Any, cast

from hypergolic.messages.persistence import load_session_messages
from hypergolic.messages.truncation import mark_messages_truncated
from hypergolic.messages.turn_compaction import _apply, _load_turn
from hypergolic.messages.types import (
    CONVERSATION_SUMMARY_PREFIX,
    TURN_SUMMARY_PREFIX,
)
from tests.conftest import make_message, make_project, make_session


REPAIR_LOGGER = "hypergolic.messages.repair"


def _texts(message) -> list[str]:
    blocks = cast(list[dict[str, Any]], message["content"])
    return [b["text"] for b in blocks if b.get("type") == "text"]


def test_truncation_survivors_merge_without_repair(caplog):
    make_project()
    sid = make_session(sid="proj-truncated")
    make_message(sid, role="user", text="first ask")
    make_message(sid, role="assistant", text="first reply")
    make_message(sid, role="user", text="second ask")
    make_message(sid, role="assistant", text="second reply")
    mark_messages_truncated(sid)
    make_message(sid, role="user", text=f"{CONVERSATION_SUMMARY_PREFIX}\n\nthe gist")

    with caplog.at_level(logging.WARNING, logger=REPAIR_LOGGER):
        loaded = load_session_messages(sid)

    assert [m["role"] for m in loaded] == ["user"]
    assert _texts(loaded[0]) == [
        "first ask",
        "second ask",
        f"{CONVERSATION_SUMMARY_PREFIX}\n\nthe gist",
    ]
    assert [r for r in caplog.records if r.name == REPAIR_LOGGER] == []


def test_compacted_turn_loads_without_repair(caplog):
    make_project()
    sid = make_session(sid="proj-compacted")
    make_message(sid, role="user", text="do the thing")
    make_message(
        sid,
        role="assistant",
        content=[{"type": "tool_use", "id": "t1", "name": "cmd", "input": {}}],
        stop_reason="tool_use",
    )
    make_message(
        sid,
        role="user",
        content=[{"type": "tool_result", "tool_use_id": "t1", "content": "done"}],
    )
    make_message(sid, role="assistant", text="thing done", stop_reason="end_turn")

    turn = _load_turn(sid)
    assert turn is not None
    _apply(sid, turn, f"{TURN_SUMMARY_PREFIX}\n\nran cmd")

    with caplog.at_level(logging.WARNING, logger=REPAIR_LOGGER):
        loaded = load_session_messages(sid)

    assert [m["role"] for m in loaded] == ["user", "assistant"]
    assert _texts(loaded[0]) == [
        "do the thing",
        f"{TURN_SUMMARY_PREFIX}\n\nran cmd",
    ]
    assert [r for r in caplog.records if r.name == REPAIR_LOGGER] == []
