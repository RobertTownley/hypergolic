import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from anthropic import BadRequestError

from hypergolic import App, TierModel
from hypergolic.config.settings import settings
from hypergolic.harness.app.state import app_context
from hypergolic.enums import ModelTier
from hypergolic.providers import (
    client_for_tier,
    generate_text,
    provider_for_tier,
    reset_client_cache,
    tier_to_model_id,
)
from hypergolic.providers import _create_aws_client
from hypergolic.providers import REQUEST_TIMEOUT
from hypergolic.providers import tier_to_thinking_config


def _response(text: str = "result") -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


async def _gen(create: AsyncMock, **kwargs):
    """Call generate_text with defaults against a mocked messages.create."""
    with patch("hypergolic.providers.client_for_tier") as mock_client:
        mock_client.return_value.messages.create = create
        return await generate_text(
            system=kwargs.pop("system", "sys"),
            messages=kwargs.pop("messages", [{"role": "user", "content": "Hi"}]),
            max_tokens=kwargs.pop("max_tokens", 100),
            **kwargs,
        )


@pytest.fixture
def fresh_client_cache():
    reset_client_cache()
    yield
    reset_client_cache()


def test_anthropic_client_disables_sdk_retries(fresh_client_cache):
    with patch("hypergolic.providers.AsyncAnthropic") as mock_cls:
        client_for_tier(ModelTier.LOW)
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["max_retries"] == 0
    assert kwargs["timeout"] is REQUEST_TIMEOUT
    assert kwargs["default_headers"] is None


def test_bedrock_tier_client(fresh_client_cache):
    tier = TierModel(id="m", provider="bedrock", aws_region="us-west-2")
    with (
        _app_with(HIGH=tier),
        patch.object(settings, "AWS_ACCESS_KEY_ID", "AKID"),
        patch.object(settings, "AWS_SECRET_ACCESS_KEY", "secret"),
        patch.object(settings, "AWS_SESSION_TOKEN", ""),
        patch("hypergolic.providers.AsyncAnthropicBedrock") as mock_cls,
    ):
        client_for_tier(ModelTier.HIGH)
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["aws_region"] == "us-west-2"
    assert kwargs["aws_access_key"] == "AKID"
    assert kwargs["aws_secret_key"] == "secret"
    assert kwargs["aws_session_token"] is None
    assert kwargs["aws_profile"] is None
    assert kwargs["max_retries"] == 0
    assert kwargs["timeout"] is REQUEST_TIMEOUT


def test_tier_headers_reach_client_and_split_cache(fresh_client_cache):
    tier = TierModel(id="m", headers={"x-client": "hypergolic"})
    with (
        _app_with(HIGH=tier),
        patch("hypergolic.providers.AsyncAnthropic") as mock_cls,
    ):
        client_for_tier(ModelTier.HIGH)
        client_for_tier(ModelTier.LOW)
    assert mock_cls.call_count == 2
    assert mock_cls.call_args_list[0].kwargs["default_headers"] == {"x-client": "hypergolic"}


def test_tier_to_model_id_defaults():
    # Defaults are the standard Anthropic model IDs, regardless of provider.
    assert tier_to_model_id(ModelTier.LOW) == "claude-haiku-4-5"
    assert tier_to_model_id(ModelTier.MEDIUM) == "claude-sonnet-4-6"
    assert tier_to_model_id(ModelTier.HIGH) == "claude-opus-4-8"


def _app_with(**models: TierModel):
    return app_context(App(models={ModelTier[k]: m for k, m in models.items()}))


def test_tier_to_model_id_app_override():
    with _app_with(
        LOW=TierModel(id="custom-low"),
        HIGH=TierModel(id="us.anthropic.claude-opus-4-8-v1:0", provider="bedrock"),
    ):
        assert tier_to_model_id(ModelTier.LOW) == "custom-low"
        assert tier_to_model_id(ModelTier.MEDIUM) == "claude-sonnet-4-6"
        assert tier_to_model_id(ModelTier.HIGH) == "us.anthropic.claude-opus-4-8-v1:0"


async def test_generate_text_returns_text():
    create = AsyncMock(return_value=_response("Hello world"))
    result = await _gen(create, system="You are helpful.")

    assert result == "Hello world"
    call_kwargs = create.call_args[1]
    assert call_kwargs["system"] == "You are helpful."
    assert call_kwargs["max_tokens"] == 100
    assert call_kwargs["messages"] == [{"role": "user", "content": "Hi"}]


@pytest.mark.parametrize("system", ["", "   "], ids=["empty", "whitespace"])
async def test_generate_text_omits_blank_system(system):
    create = AsyncMock(return_value=_response())
    await _gen(create, system=system)

    # An empty system prompt is an empty text block on the wire, which some
    # proxies reject with a 400.
    assert "system" not in create.call_args[1]


@pytest.mark.parametrize("content", [[], [_response("   \n  ").content[0]]],
                         ids=["empty", "whitespace-only"])
async def test_generate_text_returns_none_on_blank_output(content):
    response = MagicMock()
    response.content = content
    assert await _gen(AsyncMock(return_value=response)) is None


@pytest.mark.parametrize(
    "tier,model", [(ModelTier.HIGH, "claude-opus-4-8"), (ModelTier.MEDIUM, "claude-sonnet-4-6")]
)
async def test_generate_text_sets_model_for_tier(tier, model):
    create = AsyncMock(return_value=_response())
    await _gen(create, model_tier=tier)
    assert create.call_args[1]["model"] == model


def _bad_request_error(message: str) -> BadRequestError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(400, request=request)
    body = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": message},
    }
    return BadRequestError(message, response=response, body=body)


async def test_generate_text_propagates_bad_request():
    create = AsyncMock(side_effect=_bad_request_error("max_tokens too large"))
    with pytest.raises(BadRequestError):
        await _gen(create, model_tier=ModelTier.HIGH)
    assert create.call_count == 1


@pytest.mark.parametrize(
    "tier_provider,override_cls_name",
    [("mantle", "AsyncAnthropicBedrockMantle"), ("bedrock", "AsyncAnthropicBedrock")],
)
def test_client_for_tier_routes_only_overridden_tier(
    fresh_client_cache, tier_provider, override_cls_name
):
    with (
        _app_with(
            EXTRA_HIGH=TierModel(
                id="claude-fable-5", provider=tier_provider, aws_profile="fable-sso"
            )
        ),
        patch("hypergolic.providers.AsyncAnthropic") as anthropic_cls,
        patch(f"hypergolic.providers.{override_cls_name}") as override_cls,
    ):
        client_for_tier(ModelTier.HIGH)
        client_for_tier(ModelTier.EXTRA_HIGH)

    anthropic_cls.assert_called_once()
    override_cls.assert_called_once()
    assert override_cls.call_args.kwargs["aws_profile"] == "fable-sso"


def test_client_for_tier_caches_per_config(fresh_client_cache):
    with patch("hypergolic.providers.AsyncAnthropic") as anthropic_cls:
        a = client_for_tier(ModelTier.LOW)
        b = client_for_tier(ModelTier.MEDIUM)
    assert a is b
    anthropic_cls.assert_called_once()


def test_provider_for_tier_defaults_to_anthropic():
    assert provider_for_tier(ModelTier.EXTRA_HIGH) == "anthropic"


def test_provider_for_tier_override():
    with _app_with(EXTRA_HIGH=TierModel(id="claude-fable-5", provider="bedrock")):
        assert provider_for_tier(ModelTier.EXTRA_HIGH) == "bedrock"
        assert provider_for_tier(ModelTier.HIGH) == "anthropic"


async def test_aws_request_signing_runs_off_event_loop():
    # botocore credential resolution inside signing can hit disk and the
    # network; it must not run on the event loop thread (see
    # _offload_request_signing).


    client = _create_aws_client(
        "bedrock",
        {"default_headers": None},
        aws_profile=None,
        aws_region="us-east-1",
    )
    seen: dict[str, int] = {}

    def fake_get_auth_headers(**kwargs) -> dict[str, str]:
        seen["thread"] = threading.get_ident()
        return {"Authorization": "sig"}

    request = httpx2.Request("POST", "https://bedrock.example.com", content=b"{}")
    with patch("anthropic.lib.bedrock._auth.get_auth_headers", fake_get_auth_headers):
        await client._prepare_request(request)

    assert seen["thread"] != threading.get_ident()
    assert request.headers["Authorization"] == "sig"


def test_tier_to_thinking_config_skips_low_tier():
    assert tier_to_thinking_config(ModelTier.LOW) is None
    for tier in (ModelTier.MEDIUM, ModelTier.HIGH, ModelTier.EXTRA_HIGH):
        assert tier_to_thinking_config(tier) == {
            "type": "adaptive",
            "display": "summarized",
        }


async def test_client_cache_is_per_event_loop(fresh_client_cache):
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False):
        here = client_for_tier(ModelTier.LOW)
        assert client_for_tier(ModelTier.LOW) is here

        seen: list = []
        t = threading.Thread(
            target=lambda: seen.append(
                asyncio.run(_client_on_this_loop())
            )
        )
        t.start()
        t.join()
    assert seen and seen[0] is not here


async def _client_on_this_loop():
    return client_for_tier(ModelTier.LOW)
