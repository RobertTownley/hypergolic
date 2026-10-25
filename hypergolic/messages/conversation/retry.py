import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Callable, cast

import httpx2
from opentelemetry import trace
from anthropic import APIConnectionError, APIStatusError, BadRequestError
from anthropic.types import (
    Message,
    MessageParam,
    RawContentBlockStartEvent,
)

from hypergolic.enums import SessionStatus
from hypergolic.messages.conversation.interrupts import (
    _extract_partial_text,
    _persist_partial_assistant_message,
)
from hypergolic.messages.block_guards import iter_content_blocks
from hypergolic.messages.streaming import handle_streaming_event
from hypergolic.messages.types import (
    MAX_STREAM_RETRIES,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
    BroadcastFn,
    UserInterrupt,
)
from hypergolic.aws_sso import (
    actionable_sso_error,
    attempt_sso_login,
    ensure_sso_session,
    sso_auth_errors,
)
from hypergolic.telemetry.tracing import tracer
from hypergolic.providers import (
    AsyncClient,
    bedrock_profile_for_tier,
    client_for_tier,
    reset_client_cache,
    tier_model,
    tier_to_model_id,
    tier_to_thinking_config,
    uses_aws_auth,
)
from hypergolic.schemas import Session
from hypergolic.sessions.status import set_session_status_and_broadcast

logger = logging.getLogger(__name__)

# httpx2.ReadTimeout and httpx2.RemoteProtocolError are listed explicitly:
# streaming bodies are read lazily during async iteration, past the SDK's
# _request wrapping, so a mid-stream failure (after some bytes have flowed)
# propagates as a raw httpx2 error rather than an APIConnectionError.
# RemoteProtocolError covers the "peer closed connection without sending a
# complete message body (incomplete chunked read)" resets that dominate the
# long-running extra-high tier (adaptive thinking) streams.
RETRYABLE_EXCEPTIONS = (
    APIConnectionError,
    httpx2.ReadTimeout,
    httpx2.RemoteProtocolError,
)


# A generation failure arrives as an `error` SSE event on an already-200
# stream, so the status allowlist can't see it: classify by payload type.
RETRYABLE_PROVIDER_ERROR_TYPES = frozenset(
    {"api_error", "overloaded_error", "timeout_error"}
)


def _provider_error_type(exc: APIStatusError) -> str | None:
    body = exc.body
    error = body.get("error") if isinstance(body, dict) else None
    error_type = error.get("type") if isinstance(error, dict) else None
    return error_type if isinstance(error_type, str) else None


def _is_retryable_status(exc: APIStatusError) -> bool:
    if exc.status_code in (429, 500, 502, 503, 504, 529):
        return True
    return _provider_error_type(exc) in RETRYABLE_PROVIDER_ERROR_TYPES


def _retry_after_seconds(exc: Exception | None) -> float | None:
    """Server-provided Retry-After (seconds form only), if any."""
    if not isinstance(exc, APIStatusError):
        return None
    value = exc.response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _retry_delay(attempt: int, exc: Exception | None = None) -> float:
    """Exponential backoff with jitter, capped, honoring Retry-After.

    Jitter desynchronizes concurrent sessions retrying against the same
    rate-limited or degraded upstream; the cap plus MAX_STREAM_RETRIES sizes
    the total budget.
    """
    delay = min(RETRY_BASE_DELAY * 2**attempt, RETRY_MAX_DELAY)
    delay *= random.uniform(0.5, 1.5)
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(delay, RETRY_MAX_DELAY)


async def _sleep_with_cancellation(
    delay: float, check_cancelled: Callable[[], None]
) -> None:
    """Sleep in short slices so a user interrupt isn't stuck behind a
    long backoff delay."""
    remaining = delay
    while remaining > 0:
        check_cancelled()
        step = min(1.0, remaining)
        await asyncio.sleep(step)
        remaining -= step


def _with_message_cache_breakpoint(
    messages: list[MessageParam],
) -> list[MessageParam]:
    """Pin a single ephemeral cache breakpoint on the last message.

    Some proxies (e.g. LiteLLM) drop the top-level `cache_control` request
    kwarg, so we instead stamp the breakpoint directly onto the last content
    block of the last message. Skills mutate the tools/system prefix
    mid-session, so the message history is the only stable cache anchor.
    """
    if not messages:
        return messages

    blocks = iter_content_blocks(messages[-1].get("content"))
    if not blocks:
        return messages

    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    patched = list(messages)
    patched[-1] = cast(MessageParam, {**messages[-1], "content": blocks})
    return patched


@dataclass
class _StreamRequest:
    session: Session
    prompt: list[Any]
    tool_schemas: list[Any]
    messages: list[MessageParam]
    broadcast: BroadcastFn
    check_cancelled: Callable[[], None]
    tool_display_names: dict[str, str] | None
    thinking_config: Any
    streaming_started: bool = False


async def _resolve_client(
    client: AsyncClient | None, session: Session, is_aws: bool, sso_profile: Any
) -> AsyncClient:
    if client is not None:
        return client
    if is_aws and await ensure_sso_session(sso_profile):
        # A login just replaced the token cache; drop cached clients so
        # stale botocore token objects don't sign with the dead token.
        reset_client_cache()
    return client_for_tier(session.model_tier)


async def _on_stream_event(req: _StreamRequest, event: Any) -> None:
    req.check_cancelled()
    if not req.streaming_started and isinstance(event, RawContentBlockStartEvent):
        req.streaming_started = True
        trace.get_current_span().add_event("first_content_block")
        await set_session_status_and_broadcast(
            req.session.id, SessionStatus.STREAMING, req.broadcast
        )
    await handle_streaming_event(
        event, req.broadcast, req.session.id, req.tool_display_names
    )


def _usage_attributes(response: Message) -> dict[str, int]:
    usage = response.usage
    return {
        "gen_ai.usage.input_tokens": usage.input_tokens,
        "gen_ai.usage.output_tokens": usage.output_tokens,
        "gen_ai.usage.cache_read_input_tokens": usage.cache_read_input_tokens or 0,
        "gen_ai.usage.cache_creation_input_tokens": usage.cache_creation_input_tokens or 0,
    }


async def _stream_once(client: AsyncClient, req: _StreamRequest) -> Message:
    thinking_kwargs: dict[str, Any] = (
        {"thinking": req.thinking_config} if req.thinking_config is not None else {}
    )
    model = tier_to_model_id(req.session.model_tier)
    attributes = {"session.id": req.session.id, "gen_ai.request.model": model}
    try:
        with tracer.start_as_current_span("llm.stream", attributes=attributes) as span:
            async with client.messages.stream(
                max_tokens=tier_model(req.session.model_tier).max_tokens,
                model=model,
                messages=_with_message_cache_breakpoint(req.messages),
                system=req.prompt,
                tools=req.tool_schemas,
                **thinking_kwargs,
            ) as stream:
                async for event in stream:
                    await _on_stream_event(req, event)
                response = await stream.get_final_message()
            span.set_attributes(_usage_attributes(response))
        return response
    except UserInterrupt:
        partial_text = _extract_partial_text(stream)
        if partial_text:
            await _persist_partial_assistant_message(
                session_id=req.session.id, text=partial_text
            )
        raise UserInterrupt(partial_text=partial_text)


def _drop_rejected_thinking(req: _StreamRequest, exc: BadRequestError) -> bool:
    # Some proxies / older models reject the thinking parameter; drop it and
    # retry (consumes one attempt) rather than bricking the session.
    if req.thinking_config is None or "thinking" not in str(exc).lower():
        return False
    logger.warning(
        "Model %s rejected the thinking parameter; retrying without it: %s",
        tier_to_model_id(req.session.model_tier),
        exc,
    )
    req.thinking_config = None
    return True


async def _back_off(req: _StreamRequest, delay: float) -> None:
    req.streaming_started = False
    await set_session_status_and_broadcast(
        req.session.id, SessionStatus.RETRYING, req.broadcast
    )
    await _sleep_with_cancellation(delay, req.check_cancelled)


async def _retry_transient(req: _StreamRequest, attempt: int, exc: Exception) -> None:
    delay = _retry_delay(attempt)
    logger.warning(
        "Stream attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, delay,
    )
    await _back_off(req, delay)


async def _retry_status(req: _StreamRequest, attempt: int, exc: APIStatusError) -> None:
    delay = _retry_delay(attempt, exc)
    logger.warning(
        "Stream attempt %d failed (HTTP %d, %s), retrying in %.1fs",
        attempt + 1,
        exc.status_code,
        _provider_error_type(exc) or "no error type",
        delay,
    )
    await _back_off(req, delay)


async def stream_response(
    client: AsyncClient | None,
    session: Session,
    prompt: list[Any],
    tool_schemas: list[Any],
    messages: list[MessageParam],
    broadcast: BroadcastFn,
    check_cancelled: Callable[[], None],
    tool_display_names: dict[str, str] | None = None,
) -> Message:
    # Bedrock/Mantle tiers sign with AWS SSO credentials; an expired IAM
    # Identity Center session is unrecoverable by botocore's silent refresh
    # and needs an interactive `aws sso login` (see hypergolic.aws_sso).
    is_aws = uses_aws_auth(session.model_tier)
    sso_profile = bedrock_profile_for_tier(session.model_tier) if is_aws else None
    sso_errors = sso_auth_errors() if is_aws else ()
    client = await _resolve_client(client, session, is_aws, sso_profile)
    req = _StreamRequest(
        session, prompt, tool_schemas, messages, broadcast, check_cancelled,
        tool_display_names, tier_to_thinking_config(session.model_tier),
    )
    last_stream_error: Exception | None = None

    for attempt in range(MAX_STREAM_RETRIES + 1):
        can_retry = attempt < MAX_STREAM_RETRIES
        try:
            return await _stream_once(client, req)
        except BadRequestError as exc:
            if not _drop_rejected_thinking(req, exc):
                raise
            last_stream_error = exc
        except RETRYABLE_EXCEPTIONS as exc:
            last_stream_error = exc
            if can_retry:
                await _retry_transient(req, attempt, exc)
        except APIStatusError as exc:
            if not (_is_retryable_status(exc) and can_retry):
                raise
            last_stream_error = exc
            await _retry_status(req, attempt, exc)
        except sso_errors as exc:  # empty tuple (never matches) off-Bedrock
            if not (can_retry and await attempt_sso_login(sso_profile)):
                raise actionable_sso_error(sso_profile) from exc
            reset_client_cache()
            client = client_for_tier(session.model_tier)

    assert last_stream_error is not None
    raise last_stream_error
