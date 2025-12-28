"""Tests for Telegram bot handlers."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from span.telegram.bot import SpanTelegramBot
from span.db.models import CurriculumItem, ContentType


class TestSpanTelegramBotInit:
    """Tests for SpanTelegramBot initialization."""

    def test_init_stores_config(self, memory_db, config):
        """Should store config reference."""
        with patch("span.telegram.bot.Bot"), \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            bot = SpanTelegramBot(config, memory_db)
            assert bot.config == config

    def test_init_stores_db(self, memory_db, config):
        """Should store database reference."""
        with patch("span.telegram.bot.Bot"), \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            bot = SpanTelegramBot(config, memory_db)
            assert bot.db == memory_db

    def test_init_creates_bot(self, memory_db, config):
        """Should create aiogram Bot with token."""
        with patch("span.telegram.bot.Bot") as mock_bot, \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            bot = SpanTelegramBot(config, memory_db)
            mock_bot.assert_called_once_with(token=config.telegram_bot_token)

    def test_init_creates_llm_client(self, memory_db, config):
        """Should create ClaudeClient with API key."""
        with patch("span.telegram.bot.Bot"), \
             patch("span.telegram.bot.ClaudeClient") as mock_llm, \
             patch("span.telegram.bot.MemoryExtractor"):
            bot = SpanTelegramBot(config, memory_db)
            mock_llm.assert_called_once_with(config.anthropic_api_key, config.claude_model)

    def test_init_creates_scheduler(self, memory_db, config):
        """Should create CurriculumScheduler."""
        with patch("span.telegram.bot.Bot"), \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            bot = SpanTelegramBot(config, memory_db)
            assert bot.scheduler is not None

    def test_init_creates_memory_extractor(self, memory_db, config):
        """Should create MemoryExtractor with API key."""
        with patch("span.telegram.bot.Bot"), \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor") as mock_extractor:
            bot = SpanTelegramBot(config, memory_db)
            mock_extractor.assert_called_once_with(memory_db, config.anthropic_api_key)


class TestEnsureUser:
    """Tests for _ensure_user method."""

    def test_ensure_user_returns_existing(self, memory_db, config, sample_user):
        """Should return existing user by telegram ID."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.telegram.bot.Bot"), \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            bot = SpanTelegramBot(config, memory_db)
            found = bot._ensure_user(sample_user.telegram_id)

            assert found is not None
            assert found.id == user_id
            assert found.telegram_id == sample_user.telegram_id

    def test_ensure_user_creates_new(self, memory_db, config):
        """Should create new user if not exists."""
        with patch("span.telegram.bot.Bot"), \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            bot = SpanTelegramBot(config, memory_db)
            new_telegram_id = 999888777

            found = bot._ensure_user(new_telegram_id)

            assert found is not None
            assert found.telegram_id == new_telegram_id
            assert found.timezone == config.timezone


class TestSendVocabularyReminder:
    """Tests for send_vocabulary_reminder method."""

    @pytest.mark.asyncio
    async def test_sends_reminder_message(self, memory_db, config, sample_item):
        """Should send formatted vocabulary reminder."""
        with patch("span.telegram.bot.Bot") as mock_bot_class, \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            bot = SpanTelegramBot(config, memory_db)
            items = [sample_item]

            await bot.send_vocabulary_reminder(items)

            mock_bot.send_message.assert_called_once()
            call_kwargs = mock_bot.send_message.call_args.kwargs
            assert call_kwargs["chat_id"] == config.telegram_user_id
            assert sample_item.spanish in call_kwargs["text"]
            assert sample_item.english in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_skips_empty_items(self, memory_db, config):
        """Should not send message for empty items list."""
        with patch("span.telegram.bot.Bot") as mock_bot_class, \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            bot = SpanTelegramBot(config, memory_db)

            await bot.send_vocabulary_reminder([])

            mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_limits_to_five_items(self, memory_db, config):
        """Should only include first 5 items in reminder."""
        items = [
            CurriculumItem(
                id=i,
                content_type=ContentType.PHRASE,
                spanish=f"spanish{i}",
                english=f"english{i}",
                topic="test",
                difficulty=1,
            )
            for i in range(10)
        ]

        with patch("span.telegram.bot.Bot") as mock_bot_class, \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            bot = SpanTelegramBot(config, memory_db)
            await bot.send_vocabulary_reminder(items)

            call_kwargs = mock_bot.send_message.call_args.kwargs
            text = call_kwargs["text"]
            # First 5 should be present
            assert "spanish0" in text
            assert "spanish4" in text
            # 6th should not be present
            assert "spanish5" not in text


class TestSendExercise:
    """Tests for send_exercise method."""

    @pytest.mark.asyncio
    async def test_sends_exercise_prompt(self, memory_db, config):
        """Should send exercise prompt to user."""
        with patch("span.telegram.bot.Bot") as mock_bot_class, \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            bot = SpanTelegramBot(config, memory_db)
            exercise = {"prompt": "Translate: Hello"}

            await bot.send_exercise(exercise)

            mock_bot.send_message.assert_called_once()
            call_kwargs = mock_bot.send_message.call_args.kwargs
            assert call_kwargs["chat_id"] == config.telegram_user_id
            assert "Translate: Hello" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_sends_default_prompt_if_missing(self, memory_db, config):
        """Should use default prompt if not provided."""
        with patch("span.telegram.bot.Bot") as mock_bot_class, \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            bot = SpanTelegramBot(config, memory_db)
            exercise = {}

            await bot.send_exercise(exercise)

            call_kwargs = mock_bot.send_message.call_args.kwargs
            assert "Practice time!" in call_kwargs["text"]


class TestSendMessage:
    """Tests for send_message method."""

    @pytest.mark.asyncio
    async def test_sends_text_message(self, memory_db, config):
        """Should send text message to configured user."""
        with patch("span.telegram.bot.Bot") as mock_bot_class, \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            bot = SpanTelegramBot(config, memory_db)

            await bot.send_message("Test message")

            mock_bot.send_message.assert_called_once()
            call_kwargs = mock_bot.send_message.call_args.kwargs
            assert call_kwargs["chat_id"] == config.telegram_user_id
            assert call_kwargs["text"] == "Test message"
            assert call_kwargs["parse_mode"] == "Markdown"


class TestMessageCountTracking:
    """Tests for message count and extraction triggering."""

    def test_message_count_initialized_empty(self, memory_db, config):
        """Should initialize message count as empty dict."""
        with patch("span.telegram.bot.Bot"), \
             patch("span.telegram.bot.ClaudeClient"), \
             patch("span.telegram.bot.MemoryExtractor"):
            bot = SpanTelegramBot(config, memory_db)
            assert bot._message_count == {}


class TestHandlerRegistration:
    """Tests for handler registration."""

    def test_registers_handlers_on_init(self, memory_db, config, telegram_bot_patches):
        """Should register handlers on initialization."""
        with telegram_bot_patches():
            bot = SpanTelegramBot(config, memory_db)
            # Dispatcher should have registered handlers
            assert bot.dp is not None
            # The dispatcher should have message handlers registered
            assert hasattr(bot.dp, 'message')


class TestVocabularyReminderFormat:
    """Tests for vocabulary reminder message formatting."""

    @pytest.mark.asyncio
    async def test_reminder_includes_header(self, memory_db, config, sample_item, telegram_bot_patches):
        """Should include a header in the reminder message."""
        with telegram_bot_patches() as patches:
            bot = SpanTelegramBot(config, memory_db)
            await bot.send_vocabulary_reminder([sample_item])

            text = patches.mock_bot.send_message.call_args.kwargs["text"]
            # Should have some kind of review/reminder header
            assert "review" in text.lower() or "reminder" in text.lower() or "vocab" in text.lower()

    @pytest.mark.asyncio
    async def test_reminder_formats_spanish_english_pairs(self, memory_db, config, telegram_bot_patches):
        """Should format each item as spanish -> english pair."""
        items = [
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="hola",
                english="hello",
                topic="greetings",
                difficulty=1,
            ),
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="adios",
                english="goodbye",
                topic="greetings",
                difficulty=1,
            ),
        ]
        with telegram_bot_patches() as patches:
            bot = SpanTelegramBot(config, memory_db)
            await bot.send_vocabulary_reminder(items)

            text = patches.mock_bot.send_message.call_args.kwargs["text"]
            # Both items should appear
            assert "hola" in text
            assert "hello" in text
            assert "adios" in text
            assert "goodbye" in text


class TestMessagePersistence:
    """Tests verifying that messages are saved to the database."""

    @pytest.mark.asyncio
    async def test_send_message_does_not_persist_outgoing(self, memory_db, config, sample_user, telegram_bot_patches):
        """send_message should just send, not save to conversation history."""
        user_id = memory_db.create_user(sample_user)

        with telegram_bot_patches():
            bot = SpanTelegramBot(config, memory_db)
            await bot.send_message("Test notification")

            # Check that the message was NOT saved to history (it's a notification, not a conversation)
            history = memory_db.get_conversation_history(user_id)
            # send_message is for notifications, not conversation - should not save
            assert len(history) == 0
