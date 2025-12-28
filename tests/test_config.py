"""Tests for configuration management."""

import os
from unittest.mock import patch

import pytest

from span.config import (
    Config,
    DEFAULT_CLAUDE_MODEL,
    CONVERSATION_HISTORY_LIMIT,
    EXTRACTION_INTERVAL,
)


class TestConfigConstants:
    """Tests for configuration constants."""

    def test_default_claude_model_is_string(self):
        """DEFAULT_CLAUDE_MODEL should be a non-empty string."""
        assert isinstance(DEFAULT_CLAUDE_MODEL, str)
        assert len(DEFAULT_CLAUDE_MODEL) > 0

    def test_conversation_history_limit_is_positive(self):
        """CONVERSATION_HISTORY_LIMIT should be a positive integer."""
        assert isinstance(CONVERSATION_HISTORY_LIMIT, int)
        assert CONVERSATION_HISTORY_LIMIT > 0

    def test_extraction_interval_is_positive(self):
        """EXTRACTION_INTERVAL should be a positive integer."""
        assert isinstance(EXTRACTION_INTERVAL, int)
        assert EXTRACTION_INTERVAL > 0


class TestConfigDefaults:
    """Tests for Config dataclass defaults."""

    def test_config_with_minimal_args(self):
        """Config should work with only required args."""
        config = Config(anthropic_api_key="test-key")
        assert config.anthropic_api_key == "test-key"
        assert config.claude_model == DEFAULT_CLAUDE_MODEL

    def test_config_default_values(self):
        """Config should have sensible defaults."""
        config = Config(anthropic_api_key="test-key")
        assert config.daily_api_key == ""
        assert config.daily_phone_number == ""
        assert config.user_phone_number == ""
        assert config.telegram_user_id == 0
        assert config.openai_api_key == ""
        assert config.telegram_bot_token == ""
        assert config.voice_server_host == "0.0.0.0"
        assert config.voice_server_port == 7860
        assert config.database_path == "data/span.db"
        assert config.timezone == "Europe/Dublin"


class TestConfigFromEnv:
    """Tests for Config.from_env() loading."""

    def test_from_env_loads_all_vars(self):
        """from_env should load all environment variables."""
        env_vars = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "CLAUDE_MODEL": "claude-test-model",
            "DAILY_API_KEY": "daily-key",
            "DAILY_PHONE_NUMBER": "+15551234567",
            "USER_PHONE_NUMBER": "+15559876543",
            "TELEGRAM_USER_ID": "123456789",
            "OPENAI_API_KEY": "sk-openai-test",
            "TELEGRAM_BOT_TOKEN": "bot-token",
            "VOICE_SERVER_HOST": "127.0.0.1",
            "VOICE_SERVER_PORT": "8000",
            "DATABASE_PATH": "/tmp/test.db",
            "TIMEZONE": "America/Mexico_City",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            config = Config.from_env()

        assert config.anthropic_api_key == "sk-ant-test"
        assert config.claude_model == "claude-test-model"
        assert config.daily_api_key == "daily-key"
        assert config.daily_phone_number == "+15551234567"
        assert config.user_phone_number == "+15559876543"
        assert config.telegram_user_id == 123456789
        assert config.openai_api_key == "sk-openai-test"
        assert config.telegram_bot_token == "bot-token"
        assert config.voice_server_host == "127.0.0.1"
        assert config.voice_server_port == 8000
        assert config.database_path == "/tmp/test.db"
        assert config.timezone == "America/Mexico_City"

    def test_from_env_uses_defaults_for_missing(self):
        """from_env should use defaults when vars are missing."""
        env_vars = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }
        # Clear relevant env vars
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_env()

        assert config.anthropic_api_key == "sk-ant-test"
        assert config.claude_model == DEFAULT_CLAUDE_MODEL
        assert config.database_path == "data/span.db"


class TestSafeInt:
    """Tests for Config._safe_int helper."""

    def test_safe_int_valid_integer(self):
        """_safe_int should parse valid integers."""
        assert Config._safe_int("123") == 123
        assert Config._safe_int("0") == 0
        assert Config._safe_int("-5") == -5

    def test_safe_int_invalid_returns_default(self):
        """_safe_int should return default for invalid input."""
        assert Config._safe_int("not_a_number") == 0
        assert Config._safe_int("12.5") == 0  # float string
        assert Config._safe_int("") == 0

    def test_safe_int_custom_default(self):
        """_safe_int should use custom default."""
        assert Config._safe_int("invalid", default=42) == 42
        assert Config._safe_int("", default=100) == 100

    def test_safe_int_none_returns_default(self):
        """_safe_int should handle None."""
        assert Config._safe_int(None) == 0
        assert Config._safe_int(None, default=99) == 99
