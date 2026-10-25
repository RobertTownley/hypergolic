from __future__ import annotations

from typing import Any, cast

import pytest

from hypergolic.config.settings import DEFAULT_STRIP_HISTORY_THINKING
from hypergolic.harness.app.state import get_app
from hypergolic.harness.primitives.bundles import Role
from hypergolic.messages.persistence import (
    THINKING_ELIDED_STUB,
    load_session_messages,
    persist_messages,
    should_strip_thinking,
)
from tests.conftest import make_project, make_session


def _register(role_id: str, strip: bool | None) -> None:
    get_app().register_role(
        Role(id=role_id, name=role_id, prompt="p", strip_history_thinking=strip)
    )


def test_unknown_role_falls_back_to_app_setting():
    assert should_strip_thinking(None) is get_app().strip_history_thinking
    assert should_strip_thinking("nope") is get_app().strip_history_thinking


def test_missing_app_falls_back_to_default(monkeypatch):
    monkeypatch.setattr("hypergolic.harness.app.state._current_app", None)
    assert should_strip_thinking("reviewer") is DEFAULT_STRIP_HISTORY_THINKING


def test_role_default_inherits_setting(monkeypatch):
    _register("inheritor", None)
    monkeypatch.setattr(get_app(), "strip_history_thinking", False)
    assert should_strip_thinking("inheritor") is False


@pytest.mark.parametrize("override", [True, False])
def test_role_override_beats_setting(monkeypatch, override):
    _register("overrider", override)
    monkeypatch.setattr(get_app(), "strip_history_thinking", not override)
    assert should_strip_thinking("overrider") is override


async def test_loaded_history_keeps_thinking_for_opted_out_role(monkeypatch):
    monkeypatch.setattr(get_app(), "strip_history_thinking", True)
    _register("keeper", False)
    make_project()
    sid = make_session(sid="keep-thinking", role="keeper")
    await persist_messages(
        session_id=sid,
        messages=[
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "deep thought", "signature": "s"},
                    {"type": "text", "text": "hello"},
                ],
            },
        ],
    )
    blocks = cast(list[dict[str, Any]], load_session_messages(sid)[1]["content"])
    assert [b["type"] for b in blocks] == ["thinking", "text"]


async def test_loaded_history_strips_thinking_for_default_role(monkeypatch):
    monkeypatch.setattr(get_app(), "strip_history_thinking", True)
    make_project()
    sid = make_session(sid="strip-thinking")
    await persist_messages(
        session_id=sid,
        messages=[
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "deep thought", "signature": "s"}
                ],
            },
        ],
    )
    blocks = cast(list[dict[str, Any]], load_session_messages(sid)[1]["content"])
    assert blocks == [{"type": "text", "text": THINKING_ELIDED_STUB}]
