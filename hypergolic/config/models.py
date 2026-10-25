from pydantic import BaseModel, ConfigDict

from hypergolic.config.settings import Provider
from hypergolic.enums import ModelTier


class TierModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    provider: Provider = "anthropic"
    aws_profile: str | None = None
    aws_region: str | None = None
    max_tokens: int = 64_000
    headers: dict[str, str] | None = None


class SsoConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    auto_login: bool = True
    login_timeout: int = 180
    max_login_attempts: int = 3


DEFAULT_MODELS: dict[ModelTier, TierModel] = {
    ModelTier.LOW: TierModel(id="claude-haiku-4-5"),
    ModelTier.MEDIUM: TierModel(id="claude-sonnet-4-6"),
    ModelTier.HIGH: TierModel(id="claude-opus-4-8"),
    ModelTier.EXTRA_HIGH: TierModel(id="claude-fable-5"),
}
