from __future__ import annotations

import pytest

from typing import Any, cast

from datetime import datetime, timezone

from sqlalchemy import select

from hypergolic.db.engine import get_db
from hypergolic.db.models import DBMessage
from hypergolic.messages.persistence import load_session_messages
from tests.conftest import make_project, make_session

pytestmark = pytest.mark.db


def _add_message(session_id: str, role: str, text: str, created_at: datetime) -> str:
    with get_db() as db:
        m = DBMessage(
            content=[{"type": "text", "text": text}],
            session_id=session_id,
            role=role,
            created_at=created_at,
        )
        db.add(m)
        db.flush()
        return m.id


def test_sequence_assigned_monotonically_per_session():
    make_project()
    s1 = make_session(sid="seq-s1")
    s2 = make_session(sid="seq-s2")

    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    a = _add_message(s1, "user", "a", ts)
    b = _add_message(s2, "user", "b", ts)
    c = _add_message(s1, "user", "c", ts)

    with get_db() as db:
        seq = {r.id: r.sequence for r in db.scalars(select(DBMessage))}
    assert seq[a] < seq[c]
    assert seq[b] == seq[a]


def test_load_orders_by_sequence_under_same_second_collision():
    make_project()
    sid = make_session(sid="seq-collide")

    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    _add_message(sid, "user", "first", ts)
    _add_message(sid, "assistant", "second", ts)
    _add_message(sid, "user", "third", ts)

    loaded = load_session_messages(sid)
    texts: list[str] = []
    for m in loaded:
        blocks = cast(list[dict[str, Any]], m["content"])
        texts.extend(b["text"] for b in blocks if b.get("type") == "text")
    assert texts == ["first", "second", "third"]


def test_id_breaks_sequence_ties():
    make_project()
    sid = make_session(sid="seq-tie")

    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    for msg_id, text in (("m-b", "second"), ("m-a", "first")):
        with get_db() as db:
            db.add(
                DBMessage(
                    id=msg_id,
                    content=[{"type": "text", "text": text}],
                    session_id=sid,
                    role="user",
                    sequence=5,
                    created_at=ts,
                )
            )

    loaded = load_session_messages(sid)
    blocks = cast(list[dict[str, Any]], loaded[0]["content"])
    assert [b["text"] for b in blocks] == ["first", "second"]
