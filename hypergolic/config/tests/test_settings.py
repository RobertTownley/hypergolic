"""Tests for hypergolic.config.settings."""

from pathlib import Path
from unittest.mock import patch


from hypergolic.config.settings import Settings, settings
from hypergolic.config.settings import PROMPTS_DIR


def test_settings_is_singleton_instance():
    """The module-level `settings` is a Settings instance."""
    assert isinstance(settings, Settings)


def test_settings_default_api_key():
    with patch.dict("os.environ", {}, clear=True):
        s = Settings()
    assert s.HYPERGOLIC_API_KEY == ""


def test_settings_default_base_url():
    with patch.dict("os.environ", {}, clear=True):
        s = Settings()
    assert s.HYPERGOLIC_BASE_URL == "https://api.anthropic.com"


def test_settings_default_database_url_contains_hypergolic():
    with patch.dict("os.environ", {}, clear=True):
        s = Settings()
    assert "hypergolic" in s.HYPERGOLIC_DATABASE_URL


def test_settings_api_key_from_env():
    with patch.dict("os.environ", {"HYPERGOLIC_API_KEY": "sk-test-key"}):
        s = Settings()
    assert s.HYPERGOLIC_API_KEY == "sk-test-key"


def test_settings_base_url_from_env():
    with patch.dict("os.environ", {"HYPERGOLIC_BASE_URL": "https://custom.api.com"}):
        s = Settings()
    assert s.HYPERGOLIC_BASE_URL == "https://custom.api.com"


def test_settings_database_url_from_env():
    with patch.dict("os.environ", {"HYPERGOLIC_DATABASE_URL": "postgresql://u:p@h:5432/x"}):
        s = Settings()
    assert s.HYPERGOLIC_DATABASE_URL == "postgresql://u:p@h:5432/x"


def test_prompts_dir_is_path():
    assert isinstance(PROMPTS_DIR, Path)


def test_prompts_dir_points_to_base_prompts():
    assert PROMPTS_DIR.name == "prompts"
    assert PROMPTS_DIR.parent.name == "contrib"


