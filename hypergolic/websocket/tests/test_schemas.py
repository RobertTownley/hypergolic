import pytest
from pydantic import ValidationError

from hypergolic.websocket.schemas import (
    ApprovalResponseMessage,
    ConcludeSessionMessage,
    ConnectMessage,
    parse_client_message,
)


def test_parse_chat_message():
    raw = {"type": "chat", "message": "hello", "project_id": "p1"}
    msg = parse_client_message(raw)
    assert isinstance(msg, ConnectMessage)
    assert msg.message == "hello"
    assert msg.project_id == "p1"


def test_parse_chat_message_default_type():
    raw = {"message": "hello"}
    msg = parse_client_message(raw)
    assert isinstance(msg, ConnectMessage)


def test_parse_approval_response():
    raw = {
        "type": "tool_approval_response",
        "tool_use_id": "tu-1",
        "approved": True,
    }
    msg = parse_client_message(raw)
    assert isinstance(msg, ApprovalResponseMessage)
    assert msg.approved is True
    assert msg.tool_use_id == "tu-1"


def test_parse_approval_response_with_annotations():
    raw = {
        "type": "tool_approval_response",
        "tool_use_id": "tu-2",
        "approved": False,
        "denial_reason": "bad",
        "annotations": [{"highlighted_text": "foo", "comment": "bar"}],
    }
    msg = parse_client_message(raw)
    assert isinstance(msg, ApprovalResponseMessage)
    assert msg.approved is False
    assert msg.denial_reason == "bad"
    assert msg.annotations is not None and len(msg.annotations) == 1
    assert msg.annotations[0].highlighted_text == "foo"


def test_parse_conclude_session():
    raw = {
        "type": "conclude_session",
        "session_id": "s-1",
        "rating": 4,
        "feedback": "great",
    }
    msg = parse_client_message(raw)
    assert isinstance(msg, ConcludeSessionMessage)
    assert msg.session_id == "s-1"
    assert msg.rating == 4
    assert msg.feedback == "great"


def test_conclude_session_rating_bounds():
    with pytest.raises(ValidationError):
        ConcludeSessionMessage(session_id="s", rating=0)
    with pytest.raises(ValidationError):
        ConcludeSessionMessage(session_id="s", rating=6)


def test_connect_message_empty_message():
    with pytest.raises(ValidationError):
        ConnectMessage(message="")


def test_connect_message_optional_fields():
    msg = ConnectMessage(message="hi")
    assert msg.session_id is None
    assert msg.project_id is None
    assert msg.content_blocks is None
    assert msg.workflow_id is None
    assert msg.model_tier is None
