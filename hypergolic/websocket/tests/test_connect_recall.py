from typing import cast

from hypergolic.messages.types import UNSUMMARIZED_CONTENT_PREFIX
from hypergolic.websocket.connect import _user_messages
from hypergolic.websocket.schemas import ConnectMessage


def _request(content_blocks: list | None = None) -> ConnectMessage:
    return ConnectMessage(message="my question", content_blocks=content_blocks)


def _content(message: dict) -> list[dict]:
    return cast(list[dict], list(message["content"]))


def test_recall_blocks_split_into_synthesized_message():
    request = _request([{"type": "summary_recall", "text": "old transcript"}])
    messages = _user_messages(request)
    assert len(messages) == 2
    recall_text = _content(cast(dict, messages[0]))[0]["text"]
    assert recall_text.startswith(UNSUMMARIZED_CONTENT_PREFIX)
    assert recall_text.endswith("old transcript")
    assert _content(cast(dict, messages[1]))[-1] == {"type": "text", "text": "my question"}


def test_plain_message_stays_single():
    messages = _user_messages(_request())
    assert len(messages) == 1
    assert _content(cast(dict, messages[0])) == [{"type": "text", "text": "my question"}]
