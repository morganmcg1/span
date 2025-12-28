"""Shared pytest fixtures for the Span test suite."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from span.config import Config
from span.db.database import Database
from span.db.models import (
    ContentType,
    CurriculumItem,
    LearnerProfile,
    LessonSession,
    LessonType,
    User,
    UserProgress,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite database with schema initialized."""
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    db.init_schema()
    return db


@pytest.fixture
def memory_db(tmp_path):
    """Create a temporary SQLite database for fast tests.

    Note: We use a temp file instead of :memory: because SQLite
    in-memory databases don't persist between connections, and
    our Database class creates a new connection per operation.
    """
    db_path = tmp_path / "memory_test.db"
    db = Database(str(db_path))
    db.init_schema()
    return db


@pytest.fixture
def sample_user():
    """Sample user for testing."""
    return User(
        phone_number="+1234567890",
        telegram_id=123456789,
        timezone="Europe/Dublin",
    )


@pytest.fixture
def sample_item():
    """Sample curriculum item for testing."""
    return CurriculumItem(
        content_type=ContentType.PHRASE,
        spanish="¿Qué onda?",
        english="What's up?",
        example_sentence="¿Qué onda, güey? ¿Cómo estás?",
        mexican_notes="Very casual Mexican greeting. Use with friends.",
        topic="greetings",
        difficulty=1,
    )


@pytest.fixture
def sample_vocabulary_item():
    """Sample vocabulary item for testing."""
    return CurriculumItem(
        content_type=ContentType.VOCABULARY,
        spanish="chela",
        english="beer",
        example_sentence="¿Quieres una chela?",
        mexican_notes="Mexican slang for 'cerveza'.",
        topic="food",
        difficulty=2,
    )


@pytest.fixture
def sample_texting_item():
    """Sample texting abbreviation for testing."""
    return CurriculumItem(
        content_type=ContentType.TEXTING,
        spanish="xq",
        english="porque / por qué (because / why)",
        example_sentence="xq no vienes? = ¿Por qué no vienes?",
        mexican_notes="X sounds like 'por' in Spanish pronunciation rules.",
        topic="texting",
        difficulty=2,
    )


@pytest.fixture
def sample_item_with_skills():
    """Sample curriculum item with skill_contributions for skill advancement testing."""
    return CurriculumItem(
        content_type=ContentType.PHRASE,
        spanish="¡No manches!",
        english="No way! / You're kidding!",
        example_sentence="¡No manches! ¿En serio?",
        mexican_notes="Common Mexican exclamation expressing surprise.",
        topic="expressions",
        difficulty=2,
        skill_contributions={"vocabulary_production": 3, "cultural_pragmatics": 3},
    )


@pytest.fixture
def sample_learner_profile():
    """Sample learner profile for testing."""
    return LearnerProfile(
        user_id=1,
        name="Morgan",
        native_language="English",
        location="Ireland",
        level="intermediate",
        interests=["music", "travel"],
        goals=["conversational fluency"],
        strengths=["vocabulary"],
        weaknesses=["subjunctive"],
        conversation_style="casual",
    )


@pytest.fixture
def sample_session():
    """Sample lesson session for testing."""
    return LessonSession(
        user_id=1,
        lesson_type=LessonType.VOICE_CONVERSATION,
        topic="greetings",
        items_covered='["hola", "qué onda"]',
        performance_score=0.8,
        duration_seconds=300,
        notes="Good pronunciation",
    )


@pytest.fixture
def config():
    """Test configuration with fake API keys."""
    return Config(
        anthropic_api_key="test-anthropic-key",
        openai_api_key="test-openai-key",
        daily_api_key="test-daily-key",
        telegram_bot_token="test-telegram-token",
        user_phone_number="+1234567890",
        telegram_user_id=123456789,
        database_path=":memory:",
        timezone="Europe/Dublin",
    )


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "Mocked Claude response"
    mock_response.content = [mock_content]
    return mock_response


@pytest.fixture
def mock_anthropic_client(mock_anthropic_response):
    """Mock Anthropic client."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response
    return mock_client


@pytest.fixture
def mock_telegram_message():
    """Mock Telegram message object."""
    mock_message = MagicMock()
    mock_message.from_user.id = 123456789
    mock_message.text = "Hola, ¿cómo estás?"
    mock_message.message_id = 12345
    mock_message.answer = MagicMock()
    return mock_message


@pytest.fixture
def mock_telegram_voice_message():
    """Mock Telegram voice message object."""
    mock_message = MagicMock()
    mock_message.from_user.id = 123456789
    mock_message.message_id = 12346
    mock_message.voice.file_id = "voice_file_123"
    mock_message.voice.duration = 5
    mock_message.answer = MagicMock()
    mock_message.answer_voice = MagicMock()
    return mock_message


@pytest.fixture
def populated_db(memory_db, sample_user, sample_item, sample_vocabulary_item):
    """Database pre-populated with test data."""
    # Add user
    user_id = memory_db.create_user(sample_user)

    # Add curriculum items
    item1_id = memory_db.add_curriculum_item(sample_item)
    item2_id = memory_db.add_curriculum_item(sample_vocabulary_item)

    # Create progress for item1
    memory_db.get_or_create_progress(user_id, item1_id)

    return memory_db


@pytest.fixture
def telegram_bot_patches():
    """Context manager for patching Telegram bot dependencies.

    Usage:
        with telegram_bot_patches() as patches:
            bot = SpanTelegramBot(config, memory_db)
            # patches.mock_bot is the Bot mock
            # patches.mock_llm is the ClaudeClient mock
            # patches.mock_extractor is the MemoryExtractor mock
    """
    from contextlib import contextmanager
    from dataclasses import dataclass
    from unittest.mock import patch, MagicMock, AsyncMock

    @dataclass
    class Patches:
        mock_bot: MagicMock
        mock_bot_class: MagicMock
        mock_llm: MagicMock
        mock_extractor: MagicMock

    @contextmanager
    def _patches():
        with patch("span.telegram.bot.Bot") as mock_bot_class, \
             patch("span.telegram.bot.ClaudeClient") as mock_llm, \
             patch("span.telegram.bot.MemoryExtractor") as mock_extractor:
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot
            yield Patches(
                mock_bot=mock_bot,
                mock_bot_class=mock_bot_class,
                mock_llm=mock_llm,
                mock_extractor=mock_extractor,
            )

    return _patches
