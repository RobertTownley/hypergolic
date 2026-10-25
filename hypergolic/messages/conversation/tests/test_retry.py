"""Retry behavior of stream_response, incl. the regression where a mid-stream
httpx2.ReadTimeout (past APIConnectionError wrapping) failed the turn."""
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from anthropic import APIStatusError, BadRequestError
from anthropic.types import Message, MessageParam
from botocore.exceptions import TokenRetrievalError

from hypergolic.enums import ModelTier
from hypergolic.messages.conversation.retry import (
    RETRYABLE_EXCEPTIONS,
    _is_retryable_status,
    _retry_delay,
    _sleep_with_cancellation,
    stream_response,
)
from hypergolic.messages.types import (
    MAX_STREAM_RETRIES,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
    UserInterrupt,
)
from tests._factories import build_assistant_message, build_session

RETRY = "hypergolic.messages.conversation.retry"


class _FakeStream:
    """Async context manager + async iterator matching client.messages.stream()."""

    def __init__(self, *, raise_on_iter: Exception | None = None, final: Message | None = None):
        self._raise = raise_on_iter
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._raise is not None:
            raise self._raise
        raise StopAsyncIteration

    async def get_final_message(self):
        assert self._final is not None
        return self._final


def _client_with_streams(*streams: _FakeStream) -> MagicMock:
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=streams)
    return client


async def _run_stream(client, broadcast, messages=None, session=None):
    with patch(f"{RETRY}.set_session_status_and_broadcast", new=AsyncMock()):
        return await stream_response(
            client=client,
            session=session or build_session(sid="s1", project_id="p1", project_path="/tmp/p"),
            prompt=[],
            tool_schemas=[],
            messages=messages or [],
            broadcast=broadcast,
            check_cancelled=lambda: None,
        )


def _midstream_error(error_type: str = "api_error") -> APIStatusError:
    """The exception the SDK builds from a terminal `error` SSE event."""
    return APIStatusError(
        message=f"{{'type': 'error', 'error': {{'type': '{error_type}'}}}}",
        response=MagicMock(status_code=200),
        body={"type": "error", "error": {"type": error_type, "message": "boom"}},
    )


def test_retryability_classification():
    for error_type in ("api_error", "overloaded_error", "timeout_error"):
        assert _is_retryable_status(_midstream_error(error_type))
    assert not _is_retryable_status(_midstream_error("invalid_request_error"))
    # No body: classified by status code.
    assert _is_retryable_status(APIStatusError(message="x", response=MagicMock(status_code=529), body=None))
    assert _is_retryable_status(APIStatusError(message="x", response=MagicMock(status_code=504), body=None))
    assert not _is_retryable_status(APIStatusError(message="x", response=MagicMock(status_code=403), body=None))
    # Mid-stream stalls and connection resets must be retryable (regression guards).
    assert issubclass(httpx2.ReadTimeout, tuple(RETRYABLE_EXCEPTIONS))  # type: ignore[arg-type]
    assert issubclass(httpx2.RemoteProtocolError, tuple(RETRYABLE_EXCEPTIONS))  # type: ignore[arg-type]


@pytest.mark.parametrize("exc", [
    _midstream_error(),
    httpx2.RemoteProtocolError("peer closed connection without sending complete message body"),
    httpx2.ReadTimeout("stalled"),
], ids=["midstream-provider-error", "remote-protocol-error", "read-timeout"])
async def test_stream_response_retries_on_transient_errors(broadcast, exc):
    final = build_assistant_message()
    client = _client_with_streams(_FakeStream(raise_on_iter=exc), _FakeStream(final=final))
    with patch(f"{RETRY}._sleep_with_cancellation", new=AsyncMock()):
        assert await _run_stream(client, broadcast) is final
    assert client.messages.stream.call_count == 2


async def test_stream_response_uses_exponential_backoff(broadcast):
    """Delays double per attempt: 1s, 2s, 4s (jitter pinned to 1.0)."""
    final = build_assistant_message()
    client = _client_with_streams(
        *[_FakeStream(raise_on_iter=httpx2.ReadTimeout("")) for _ in range(3)],
        _FakeStream(final=final),
    )
    sleep_mock = AsyncMock()
    with (
        patch(f"{RETRY}._sleep_with_cancellation", new=sleep_mock),
        patch(f"{RETRY}.random.uniform", return_value=1.0),
    ):
        assert await _run_stream(client, broadcast) is final

    assert client.messages.stream.call_count == 4
    delays = [call.args[0] for call in sleep_mock.call_args_list]
    assert delays == [RETRY_BASE_DELAY * 1, RETRY_BASE_DELAY * 2, RETRY_BASE_DELAY * 4]


def test_retry_delay_knobs():
    assert MAX_STREAM_RETRIES == 8
    assert RETRY_MAX_DELAY == 10.0
    with patch(f"{RETRY}.random.uniform", return_value=1.5):
        assert _retry_delay(attempt=20) == RETRY_MAX_DELAY
    for attempt in (0, 3):
        base = min(RETRY_BASE_DELAY * 2**attempt, RETRY_MAX_DELAY)
        delays = {_retry_delay(attempt) for _ in range(50)}
        assert all(base * 0.5 <= d <= base * 1.5 for d in delays)
        assert len(delays) > 1


@pytest.mark.parametrize("header, expected", [
    ("5", 5.0),
    ("600", RETRY_MAX_DELAY),
    ("Wed, 21 Oct 2026 07:28:00 GMT", RETRY_BASE_DELAY),
], ids=["honored", "capped", "unparseable-ignored"])
def test_retry_delay_retry_after_header(header, expected):
    response = MagicMock(status_code=429)
    response.headers = httpx2.Headers({"retry-after": header})
    exc = APIStatusError("err", response=response, body=None)
    with patch(f"{RETRY}.random.uniform", return_value=1.0):
        assert _retry_delay(attempt=0, exc=exc) == expected


async def test_sleep_with_cancellation_slices_sleep():
    sleep_mock = AsyncMock()
    with patch(f"{RETRY}.asyncio.sleep", new=sleep_mock):
        await _sleep_with_cancellation(3.5, lambda: None)
    assert [call.args[0] for call in sleep_mock.call_args_list] == [1.0, 1.0, 1.0, 0.5]


async def test_sleep_with_cancellation_aborts_on_interrupt():
    calls = 0

    def check_cancelled() -> None:
        nonlocal calls
        calls += 1
        if calls > 2:
            raise UserInterrupt()

    with patch(f"{RETRY}.asyncio.sleep", new=AsyncMock()), pytest.raises(UserInterrupt):
        await _sleep_with_cancellation(60.0, check_cancelled)
    assert calls == 3


async def test_stream_response_pins_cache_control_on_last_message(broadcast):
    """The ephemeral breakpoint must be stamped onto the last message block.

    Proxies like LiteLLM drop the top-level `cache_control` request kwarg, so
    the message-layer breakpoint is our only prompt-cache anchor (skills mutate
    the tools/system prefix mid-session). Guard it against silent removal.
    """
    client = _client_with_streams(_FakeStream(final=build_assistant_message()))
    messages: list[MessageParam] = [
        {"role": "user", "content": "first"},
        {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]},
    ]
    await _run_stream(client, broadcast, messages)

    kwargs = client.messages.stream.call_args.kwargs
    assert "cache_control" not in kwargs
    sent = kwargs["messages"]
    last_blocks = sent[-1]["content"]
    assert last_blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in last_blocks[0]
    breakpoints = [
        b for msg in sent
        for b in (msg["content"] if isinstance(msg["content"], list) else [])
        if "cache_control" in b
    ]
    assert len(breakpoints) == 1


async def test_request_adds_no_text_after_the_breakpoint(broadcast):
    client = _client_with_streams(_FakeStream(final=build_assistant_message()))
    messages: list[MessageParam] = [{"role": "user", "content": [{"type": "text", "text": "a"}]}]
    await _run_stream(client, broadcast, messages)

    last_blocks = client.messages.stream.call_args.kwargs["messages"][-1]["content"]
    assert last_blocks == [{"type": "text", "text": "a", "cache_control": {"type": "ephemeral"}}]
    assert messages[0]["content"] == [{"type": "text", "text": "a"}]


@contextmanager
def _bedrock_env(**overrides):
    """Patch retry's provider resolution to simulate a Bedrock tier."""
    defaults = {
        "uses_aws_auth": lambda tier: True,
        "bedrock_profile_for_tier": lambda tier: "rr-nonprod",
    }
    defaults.update(overrides)
    with ExitStack() as stack:
        for name, value in defaults.items():
            stack.enter_context(patch(f"{RETRY}.{name}", value))
        yield


def _sso_error():
    return TokenRetrievalError(provider="sso", error_msg="Token has expired and refresh failed")


async def test_stream_response_recovers_from_expired_sso(broadcast):
    """An expired IAM Identity Center session mid-turn: `aws sso login`
    succeeds, cached clients are rebuilt, and the turn completes."""
    final = build_assistant_message()
    dead_client = _client_with_streams()
    dead_client.messages.stream = MagicMock(side_effect=_sso_error())
    fresh_client = _client_with_streams(_FakeStream(final=final))
    login = AsyncMock(return_value=True)
    reset = MagicMock()

    with _bedrock_env(
        attempt_sso_login=login,
        reset_client_cache=reset,
        client_for_tier=lambda tier: fresh_client,
    ):
        assert await _run_stream(dead_client, broadcast) is final
    login.assert_awaited_once_with("rr-nonprod")
    reset.assert_called_once()


async def test_stream_response_raises_actionable_error_when_login_fails(broadcast):
    dead_client = _client_with_streams()
    dead_client.messages.stream = MagicMock(side_effect=_sso_error())
    with _bedrock_env(attempt_sso_login=AsyncMock(return_value=False)):
        with pytest.raises(RuntimeError, match="aws sso login --profile rr-nonprod"):
            await _run_stream(dead_client, broadcast)


async def test_stream_response_ignores_sso_plumbing_off_bedrock(broadcast):
    """Anthropic-provider tiers must never probe SSO or resolve profiles."""
    client = _client_with_streams(_FakeStream(final=build_assistant_message()))
    ensure = AsyncMock()
    with patch(f"{RETRY}.ensure_sso_session", ensure):
        await _run_stream(client, broadcast)
    ensure.assert_not_awaited()


def _bad_request(message: str) -> Exception:
    return BadRequestError(
        message,
        response=httpx2.Response(400, request=httpx2.Request("POST", "https://api.anthropic.com")),
        body={"error": {"message": message}},
    )


async def test_thinking_config_by_tier(broadcast):
    """Non-low tiers request adaptive thinking with visible summaries; LOW omits it."""
    client = _client_with_streams(_FakeStream(final=build_assistant_message()))
    await _run_stream(client, broadcast)  # MEDIUM tier
    assert client.messages.stream.call_args.kwargs["thinking"] == {
        "type": "adaptive", "display": "summarized",
    }

    client = _client_with_streams(_FakeStream(final=build_assistant_message()))
    low = build_session(sid="s1", project_id="p1", project_path="/tmp/p", model_tier=ModelTier.LOW)
    await _run_stream(client, broadcast, session=low)
    assert "thinking" not in client.messages.stream.call_args.kwargs


async def test_stream_response_retries_without_thinking_on_rejection(broadcast):
    final = build_assistant_message()
    client = _client_with_streams(
        _FakeStream(raise_on_iter=_bad_request("Unexpected parameter: thinking")),
        _FakeStream(final=final),
    )
    assert await _run_stream(client, broadcast) is final
    assert client.messages.stream.call_count == 2
    assert "thinking" in client.messages.stream.call_args_list[0].kwargs
    assert "thinking" not in client.messages.stream.call_args_list[1].kwargs


async def test_stream_response_reraises_unrelated_bad_request(broadcast):
    client = _client_with_streams(_FakeStream(raise_on_iter=_bad_request("max_tokens too large")))
    with pytest.raises(BadRequestError):
        await _run_stream(client, broadcast)
    assert client.messages.stream.call_count == 1
