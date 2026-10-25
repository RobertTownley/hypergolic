"""Tests for repair_message_sequence in hypergolic.messages.repair."""

import logging
from typing import Any, cast

from anthropic.types import MessageParam, TextBlockParam, ToolUseBlockParam

from hypergolic.messages.repair import repair_message_sequence


def _user(text: str) -> MessageParam:
    block: TextBlockParam = {"type": "text", "text": text}
    return MessageParam(role="user", content=[block])


def _assistant(text: str) -> MessageParam:
    block: TextBlockParam = {"type": "text", "text": text}
    return MessageParam(role="assistant", content=[block])


def _assistant_tool_use(tool_id: str) -> MessageParam:
    block: ToolUseBlockParam = {"type": "tool_use", "id": tool_id, "name": "test", "input": {}}
    return MessageParam(role="assistant", content=[block])


def _content_list(msg: MessageParam) -> list[Any]:
    return cast(list[Any], msg["content"])


def test_empty_list():
    assert repair_message_sequence([]) == []


def test_no_repair_needed():
    msgs = [_user("hello"), _assistant("hi")]
    result = repair_message_sequence(msgs)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"


def test_consecutive_user_messages_merged(caplog: Any):
    msgs = [_user("a"), _user("b")]
    with caplog.at_level(logging.WARNING, logger="hypergolic.messages.repair"):
        result = repair_message_sequence(msgs)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert len(_content_list(result[0])) == 2
    assert "merging consecutive user messages" in caplog.text


def test_consecutive_assistant_messages_merged(caplog: Any):
    msgs = [_user("start"), _assistant("a"), _assistant("b")]
    with caplog.at_level(logging.WARNING, logger="hypergolic.messages.repair"):
        result = repair_message_sequence(msgs)
    assert len(result) == 2
    assert result[1]["role"] == "assistant"
    assert len(_content_list(result[1])) == 2
    assert "merging consecutive assistant messages" in caplog.text


def test_assistant_tool_use_followed_by_assistant_inserts_synthetic(caplog: Any):
    msgs = [_user("go"), _assistant_tool_use("tool_1"), _assistant("done")]
    with caplog.at_level(logging.WARNING, logger="hypergolic.messages.repair"):
        result = repair_message_sequence(msgs)
    # user, assistant(tool_use), user(synthetic tool_result), assistant(done)
    assert len(result) == 4
    assert result[2]["role"] == "user"
    content = _content_list(result[2])
    tool_result = content[0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tool_1"
    assert tool_result["is_error"] is True
    assert "inserting synthetic tool_results" in caplog.text


def test_trailing_tool_use_gets_synthetic_result(caplog: Any):
    msgs = [_user("go"), _assistant_tool_use("tool_2")]
    with caplog.at_level(logging.WARNING, logger="hypergolic.messages.repair"):
        result = repair_message_sequence(msgs)
    assert len(result) == 3
    assert result[2]["role"] == "user"
    content = _content_list(result[2])
    assert content[0]["tool_use_id"] == "tool_2"
    assert "appending synthetic tool_results for trailing tool_use" in caplog.text


def test_log_includes_session_and_message_id(caplog: Any):
    msgs = [_user("a"), _user("b")]
    with caplog.at_level(logging.WARNING, logger="hypergolic.messages.repair"):
        repair_message_sequence(msgs, session_id="sess-456", message_ids=["msg-A", "msg-B"])
    assert "session=sess-456" in caplog.text
    assert "message=msg-B" in caplog.text


def test_no_context_when_no_ids_provided(caplog: Any):
    msgs = [_user("a"), _user("b")]
    with caplog.at_level(logging.WARNING, logger="hypergolic.messages.repair"):
        repair_message_sequence(msgs)
    assert "session=" not in caplog.text
    assert "message=" not in caplog.text
    assert "merging consecutive user messages" in caplog.text


def test_string_content_converted_to_blocks():
    msg = MessageParam(role="user", content="hello")
    msgs = [msg, _user("world")]
    result = repair_message_sequence(msgs)
    assert len(result) == 1
    content = _content_list(result[0])
    assert content[0] == {"type": "text", "text": "hello"}
    assert content[1] == {"type": "text", "text": "world"}


def test_none_message_ids_handled():
    msgs = [_user("a"), _user("b")]
    # message_ids with None entries should not crash
    result = repair_message_sequence(msgs, session_id="s1", message_ids=[None, None])
    assert len(result) == 1


def _tool_result(tool_id: str) -> MessageParam:
    return MessageParam(
        role="user",
        content=cast(
            Any,
            [{"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "text", "text": "ok"}]}],
        ),
    )


def test_user_message_missing_tool_result_gets_synthetic_prepended(caplog: Any):
    """Restart-during-approval shape: assistant tool_use, then a fresh user prompt."""
    msgs = [_user("start"), _assistant_tool_use("tid-1"), _user("are you there?")]
    with caplog.at_level(logging.WARNING, logger="hypergolic.messages.repair"):
        result = repair_message_sequence(msgs)
    assert len(result) == 3
    blocks = _content_list(result[2])
    assert blocks[0]["type"] == "tool_result"
    assert blocks[0]["tool_use_id"] == "tid-1"
    assert blocks[0]["is_error"] is True
    assert blocks[1] == {"type": "text", "text": "are you there?"}
    assert "prepending synthetic tool_results" in caplog.text


def test_user_message_with_partial_tool_results_gets_missing_prepended():
    tool_uses: list[Any] = [
        {"type": "tool_use", "id": "tid-1", "name": "test", "input": {}},
        {"type": "tool_use", "id": "tid-2", "name": "test", "input": {}},
    ]
    msgs = [
        _user("start"),
        MessageParam(role="assistant", content=cast(Any, tool_uses)),
        _tool_result("tid-1"),
    ]
    result = repair_message_sequence(msgs)
    assert len(result) == 3
    blocks = _content_list(result[2])
    result_ids = [b["tool_use_id"] for b in blocks if b["type"] == "tool_result"]
    assert set(result_ids) == {"tid-1", "tid-2"}


def test_user_message_with_complete_tool_results_untouched():
    msgs = [_user("start"), _assistant_tool_use("tid-1"), _tool_result("tid-1")]
    result = repair_message_sequence(msgs)
    assert len(result) == 3
    assert len(_content_list(result[2])) == 1


def test_empty_content_message_stubbed(caplog):
    msgs = [_user("start"), MessageParam(role="assistant", content=cast(Any, []))]
    with caplog.at_level("WARNING"):
        result = repair_message_sequence(msgs)
    assert _content_list(result[1]) == [{"type": "text", "text": "(empty message)"}]
    assert "empty-content" in caplog.text


def test_empty_string_content_stubbed():
    msgs = [_user("start"), MessageParam(role="assistant", content="")]
    result = repair_message_sequence(msgs)
    assert _content_list(result[1]) == [{"type": "text", "text": "(empty message)"}]
