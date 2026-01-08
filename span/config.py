"""Configuration management for Span."""

# This module centralizes all environment variable loading and configuration
# for the Span application, including API keys, server settings, and database paths.

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

# Default Claude model - use this constant for consistency
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

# Memory and context limits
CONVERSATION_HISTORY_LIMIT = 20  # Messages to load as working memory
EXTRACTION_INTERVAL = 5  # Extract facts every N message pairs


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Anthropic
    anthropic_api_key: str
    claude_model: str = DEFAULT_CLAUDE_MODEL

    # Daily / Pipecat Cloud
    daily_api_key: str = ""
    daily_phone_number: str = ""

    # User
    user_phone_number: str = ""
    telegram_user_id: int = 0

    # OpenAI (gpt-realtime for voice)
    openai_api_key: str = ""

    # Telegram
    telegram_bot_token: str = ""

    # Server
    voice_server_host: str = "0.0.0.0"
    voice_server_port: int = 7860
    voice_server_public_url: str = ""  # e.g., http://135.181.102.44:7860 for production
    voice_server_auth_token: str = ""

    # Database
    database_path: str = "data/span.db"

    # Timezone
    timezone: str = "Europe/Dublin"

    @staticmethod
    def _safe_int(value: str, default: int = 0) -> int:
        """Safely parse an integer, returning default if invalid."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "Config":
        """Load configuration from environment variables."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            claude_model=os.environ.get("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
            daily_api_key=os.environ.get("DAILY_API_KEY", ""),
            daily_phone_number=os.environ.get("DAILY_PHONE_NUMBER", ""),
            user_phone_number=os.environ.get("USER_PHONE_NUMBER", ""),
            telegram_user_id=cls._safe_int(os.environ.get("TELEGRAM_USER_ID", "0")),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            voice_server_host=os.environ.get("VOICE_SERVER_HOST", "0.0.0.0"),
            voice_server_port=cls._safe_int(os.environ.get("VOICE_SERVER_PORT", "7860"), 7860),
            voice_server_public_url=os.environ.get("VOICE_SERVER_PUBLIC_URL", ""),
            voice_server_auth_token=os.environ.get("VOICE_SERVER_AUTH_TOKEN", ""),
            database_path=os.environ.get("DATABASE_PATH", "data/span.db"),
            timezone=os.environ.get("TIMEZONE", "Europe/Dublin"),
        )

    def ensure_database_dir(self) -> None:
        """Ensure the database directory exists."""
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
