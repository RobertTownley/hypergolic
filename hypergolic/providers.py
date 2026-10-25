import asyncio
from weakref import WeakKeyDictionary
from typing import TypedDict

import httpx2
from anthropic import AsyncAnthropic
from anthropic import AsyncAnthropicBedrock
from anthropic.lib.bedrock import AsyncAnthropicBedrockMantle
from anthropic.types import MessageParam, ModelParam, ThinkingConfigParam

from hypergolic.config.models import DEFAULT_MODELS, TierModel
from hypergolic.config.settings import Provider, settings
from hypergolic.enums import ModelTier
from hypergolic.harness.app.state import get_app

AsyncClient = AsyncAnthropic | AsyncAnthropicBedrock | AsyncAnthropicBedrockMantle

_AWS_PROVIDERS: frozenset[Provider] = frozenset({"bedrock", "mantle"})


class ClientConfig(TypedDict):
    default_headers: dict | None


def tier_model(tier: ModelTier) -> TierModel:
    try:
        return get_app().models[tier]
    except RuntimeError:
        return DEFAULT_MODELS[tier]


def provider_for_tier(tier: ModelTier) -> Provider:
    return tier_model(tier).provider


def uses_aws_auth(tier: ModelTier) -> bool:
    """True when this tier's provider signs with AWS credentials (SSO-capable)."""
    return provider_for_tier(tier) in _AWS_PROVIDERS


def bedrock_profile_for_tier(tier: ModelTier) -> str | None:
    return tier_model(tier).aws_profile


def _bedrock_region_for_tier(tier: ModelTier) -> str | None:
    return tier_model(tier).aws_region


# The SDK default is a flat 10 minutes, so a hung request (Bedrock accepting
# the connection but never sending response headers) stalls a session for 10
# minutes before the retry loop sees it. A 2-minute read timeout still
# tolerates slow first tokens on large cached contexts; live streams emit
# events far more often than that.
REQUEST_TIMEOUT = httpx2.Timeout(connect=15.0, read=120.0, write=120.0, pool=60.0)


def _client_config(tier: ModelTier) -> ClientConfig:
    return {"default_headers": tier_model(tier).headers}


def _offload_request_signing(
    client: AsyncAnthropicBedrock | AsyncAnthropicBedrockMantle,
) -> None:
    """Move per-request AWS SigV4 signing off the event loop.

    The SDK's async ``_prepare_request`` signs synchronously via botocore:
    resolving SSO credentials there reads the token cache from disk and — when
    the cached role credentials are stale — makes blocking network calls
    (token refresh, GetRoleCredentials). On the shared event loop that stalls
    every session, so run the SDK's own signing coroutine on a worker thread.
    """
    inner = client._prepare_request

    async def _prepare_request(request: httpx2.Request) -> None:
        # Create the coroutine inside the worker so a cancellation before
        # the thread starts can't leave it never-awaited.
        await asyncio.to_thread(lambda: asyncio.run(inner(request)))

    client._prepare_request = _prepare_request  # ty: ignore[invalid-assignment]


def _create_aws_client(
    provider: Provider,
    client_config: ClientConfig,
    *,
    aws_profile: str | None,
    aws_region: str | None,
) -> AsyncAnthropicBedrock | AsyncAnthropicBedrockMantle:
    # Bedrock and Mantle SDK clients accept the same AWS constructor kwargs and
    # resolve their (different) endpoints internally from the region. Resolve
    # the class off the module at call time (not a module-level dict) so tests
    # patching `AsyncAnthropicBedrock` / `AsyncAnthropicBedrockMantle` take hold.
    cls = (
        AsyncAnthropicBedrock if provider == "bedrock" else AsyncAnthropicBedrockMantle
    )
    client = cls(
        aws_region=aws_region,
        aws_access_key=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_key=settings.AWS_SECRET_ACCESS_KEY or None,
        aws_session_token=settings.AWS_SESSION_TOKEN or None,
        aws_profile=aws_profile,
        max_retries=0,
        timeout=REQUEST_TIMEOUT,
        **client_config,
    )
    _offload_request_signing(client)
    return client


def _create_anthropic_client(client_config: ClientConfig) -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key=settings.HYPERGOLIC_API_KEY,
        base_url=settings.HYPERGOLIC_BASE_URL,
        # We run our own retry loop (with partial-message persistence and
        # session status broadcasting) in `messages.conversation.retry`, so
        # disable the SDK's built-in retries to avoid double-retrying.
        max_retries=0,
        timeout=REQUEST_TIMEOUT,
        **client_config,
    )


# Cache one client per (event loop, provider configuration): httpx pools bind
# their primitives to the loop that opens their connections, so a cached
# client must never cross loops (the CLI runs two — main + broker thread).
_client_caches: "WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple, AsyncClient]]" = (
    WeakKeyDictionary()
)
_no_loop_cache: dict[tuple, AsyncClient] = {}


def _client_cache() -> dict[tuple, AsyncClient]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return _no_loop_cache
    return _client_caches.setdefault(loop, {})


def _cache_key(tier: ModelTier, provider: Provider) -> tuple:
    headers = tuple(sorted((tier_model(tier).headers or {}).items()))
    if provider in _AWS_PROVIDERS:
        return (
            provider,
            bedrock_profile_for_tier(tier),
            _bedrock_region_for_tier(tier),
            headers,
        )
    return ("anthropic", headers)


def client_for_tier(tier: ModelTier) -> AsyncClient:
    provider = provider_for_tier(tier)
    key = _cache_key(tier, provider)
    cache = _client_cache()
    client = cache.get(key)
    if client is None:
        if provider in _AWS_PROVIDERS:
            client = _create_aws_client(
                provider,
                _client_config(tier),
                aws_profile=bedrock_profile_for_tier(tier),
                aws_region=_bedrock_region_for_tier(tier),
            )
        else:
            client = _create_anthropic_client(_client_config(tier))
        cache[key] = client
    return client


def reset_client_cache() -> None:
    """Drop all cached clients so the next `client_for_tier` rebuilds them.

    Clients are built once and cached for the process lifetime. Bedrock clients
    using SSO / instance profiles refresh credentials per-request via botocore,
    so they do not need invalidation; static AWS keys are frozen until this is
    called. Primarily used by tests.
    """
    _client_caches.clear()
    _no_loop_cache.clear()


def tier_to_model_id(tier: ModelTier) -> ModelParam:
    return tier_model(tier).id


def tier_to_thinking_config(tier: ModelTier) -> ThinkingConfigParam | None:
    """Thinking config for the main conversation stream.

    Adaptive thinking with explicitly visible (summarized) thinking text —
    some models default display to "omitted", returning empty thinking
    blocks. The low tier (Haiku) doesn't support adaptive thinking, so it
    gets no config.
    """
    if tier is ModelTier.LOW:
        return None
    return {"type": "adaptive", "display": "summarized"}


async def generate_text(
    *,
    system: str,
    messages: list[MessageParam],
    max_tokens: int,
    model_tier: ModelTier = ModelTier.LOW,
) -> str | None:
    client = client_for_tier(model_tier)
    kwargs: dict = {
        "max_tokens": max_tokens,
        "model": tier_to_model_id(model_tier),
        "messages": messages,
    }
    # An empty system prompt is an empty text block on the wire, which some
    # proxies reject outright ("text content blocks must be non-empty").
    if system.strip():
        kwargs["system"] = system
    response = await client.messages.create(**kwargs)
    text = "".join(
        getattr(b, "text", "")
        for b in response.content
        if getattr(b, "type", None) == "text"
    ).strip()
    return text or None
