from unittest.mock import MagicMock

import pytest
from anthropic import APIConnectionError, APIStatusError

from hypergolic.db import audit_rows as audit_rows_module
from hypergolic.db.models import DBError
from hypergolic.sessions.errors import (
    format_error_detail,
    persist_error,
    persist_error_message,
)


def test_format_error_detail_generic():
    assert format_error_detail(ValueError("oops")) == "oops"


def test_format_error_detail_api_connection():
    result = format_error_detail(APIConnectionError(request=MagicMock()))
    assert "Lost connection" in result


def test_format_error_detail_api_status():
    exc = APIStatusError(
        message="overloaded",
        response=MagicMock(status_code=529),
        body=None,
    )
    result = format_error_detail(exc)
    assert "529" in result
    assert "overloaded" in result


def test_format_error_detail_midstream_avoids_http_200():
    exc = APIStatusError(
        message="internal server error",
        response=MagicMock(status_code=200),
        body={"type": "error", "error": {"type": "api_error"}},
    )
    result = format_error_detail(exc)
    assert "200" not in result
    assert "mid-stream" in result


def test_format_error_detail_generic_empty_falls_back_to_class():
    class Weird(Exception):
        pass

    assert format_error_detail(Weird()) == "Weird"


def test_format_error_detail_api_connection_empty_inner():
    exc = APIConnectionError(request=MagicMock())
    exc.message = ""
    result = format_error_detail(exc)
    assert result.strip() != ""
    assert "Lost connection" in result


def test_persist_error_message(message_rows):
    persist_error_message("s-1", "something broke")
    [added] = message_rows.for_session("s-1")
    assert (added.role, added.stop_reason) == ("assistant", "error")
    assert added.content == [{"type": "text", "text": "something broke"}]


@pytest.mark.parametrize("detail", ["", "   \n\t  "])
def test_persist_error_message_blank_detail_uses_fallback(message_rows, detail):
    persist_error_message("s-1", detail)
    assert message_rows.for_session("s-1")[0].content[0]["text"].strip() != ""


def test_persist_error(audit_rows):
    persist_error("s-1", ValueError("boom"))
    [added] = audit_rows.of(DBError)
    assert (added.session_id, added.error_type) == ("s-1", "ValueError")


def test_persist_error_swallows_exception(monkeypatch):
    monkeypatch.setattr(audit_rows_module, "insert", MagicMock(side_effect=RuntimeError))
    persist_error("s-1", ValueError("boom"))
