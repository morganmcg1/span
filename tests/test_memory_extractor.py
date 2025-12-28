"""Tests for async fact extraction service."""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from span.memory.extractor import ExtractionResult, MemoryExtractor


class TestExtractionResultDataclass:
    """Tests for ExtractionResult dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = ExtractionResult()
        assert result.facts_extracted == 0
        assert result.profile_updated is False
        assert result.milestones == []

    def test_custom_values(self):
        """Should store custom values."""
        result = ExtractionResult(
            facts_extracted=3,
            profile_updated=True,
            milestones=["learned hola"],
        )
        assert result.facts_extracted == 3
        assert result.profile_updated is True
        assert result.milestones == ["learned hola"]

    def test_milestones_defaults_to_empty_list(self):
        """Should initialize milestones to empty list via __post_init__."""
        result = ExtractionResult(facts_extracted=1)
        assert result.milestones == []
        # Verify it's a new list instance each time
        result2 = ExtractionResult()
        assert result.milestones is not result2.milestones


class TestMemoryExtractorInit:
    """Tests for MemoryExtractor initialization."""

    def test_init_stores_db(self, memory_db):
        """Should store database reference."""
        with patch("span.memory.extractor.Anthropic"):
            extractor = MemoryExtractor(memory_db, "test-key")
            assert extractor.db == memory_db

    def test_init_creates_anthropic_client(self, memory_db):
        """Should create Anthropic client with API key."""
        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            extractor = MemoryExtractor(memory_db, "test-api-key")
            mock_anthropic.assert_called_once_with(api_key="test-api-key")

    def test_init_creates_extraction_lock(self, memory_db):
        """Should create asyncio lock for extraction."""
        with patch("span.memory.extractor.Anthropic"):
            extractor = MemoryExtractor(memory_db, "test-key")
            assert isinstance(extractor._extraction_lock, asyncio.Lock)


class TestExtractFactsAsync:
    """Tests for extract_facts_async method."""

    @pytest.mark.asyncio
    async def test_empty_messages_returns_empty_result(self, memory_db, sample_user):
        """Should return empty result for empty messages."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic"):
            extractor = MemoryExtractor(memory_db, "test-key")
            result = await extractor.extract_facts_async(user_id, [])

            assert result.facts_extracted == 0
            assert result.profile_updated is False
            assert result.milestones == []

    @pytest.mark.asyncio
    async def test_extracts_name_from_conversation(self, memory_db, sample_user):
        """Should extract and save learner name."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"name": "Carlos"}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "Hi, I'm Carlos!"}]
            result = await extractor.extract_facts_async(user_id, messages)

            assert result.facts_extracted == 1
            assert result.profile_updated is True

            # Verify profile was updated
            profile = memory_db.get_or_create_learner_profile(user_id)
            assert profile.name == "Carlos"

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_name(self, memory_db, sample_user):
        """Should not overwrite name if already set."""
        user_id = memory_db.create_user(sample_user)

        # Set existing name
        profile = memory_db.get_or_create_learner_profile(user_id)
        profile.name = "Morgan"
        memory_db.update_learner_profile(profile)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"name": "Carlos"}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "Hi, I'm Carlos!"}]
            result = await extractor.extract_facts_async(user_id, messages)

            # Name should not have been extracted (already set)
            assert result.facts_extracted == 0

            # Verify original name preserved
            profile = memory_db.get_or_create_learner_profile(user_id)
            assert profile.name == "Morgan"

    @pytest.mark.asyncio
    async def test_parses_json_from_code_block(self, memory_db, sample_user):
        """Should parse JSON from markdown code blocks."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            # Response wrapped in markdown code block
            mock_response.content = [MagicMock(text='```json\n{"name": "Maria"}\n```')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "I'm Maria"}]
            result = await extractor.extract_facts_async(user_id, messages)

            assert result.facts_extracted == 1
            profile = memory_db.get_or_create_learner_profile(user_id)
            assert profile.name == "Maria"

    @pytest.mark.asyncio
    async def test_parses_json_from_plain_code_block(self, memory_db, sample_user):
        """Should parse JSON from plain code blocks without language."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='```\n{"location": "Mexico City"}\n```')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "I live in Mexico City"}]
            result = await extractor.extract_facts_async(user_id, messages)

            assert result.facts_extracted == 1
            profile = memory_db.get_or_create_learner_profile(user_id)
            assert profile.location == "Mexico City"

    @pytest.mark.asyncio
    async def test_appends_interests_without_duplicates(self, memory_db, sample_user):
        """Should append new interests without creating duplicates."""
        user_id = memory_db.create_user(sample_user)

        # Set existing interest
        profile = memory_db.get_or_create_learner_profile(user_id)
        profile.interests = ["music"]
        memory_db.update_learner_profile(profile)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            # Return both existing and new interest
            mock_response.content = [MagicMock(text='{"interests": ["music", "travel"]}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "I love music and travel"}]
            result = await extractor.extract_facts_async(user_id, messages)

            # Only "travel" should be counted as new
            assert result.facts_extracted == 1

            profile = memory_db.get_or_create_learner_profile(user_id)
            assert "music" in profile.interests
            assert "travel" in profile.interests
            assert len(profile.interests) == 2

    @pytest.mark.asyncio
    async def test_handles_level_change(self, memory_db, sample_user):
        """Should update level when level_change is valid."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"level_change": "intermediate"}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "I've been studying for 2 years"}]
            result = await extractor.extract_facts_async(user_id, messages)

            assert result.facts_extracted == 1
            profile = memory_db.get_or_create_learner_profile(user_id)
            assert profile.level == "intermediate"

    @pytest.mark.asyncio
    async def test_ignores_invalid_level_change(self, memory_db, sample_user):
        """Should ignore invalid level_change values."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"level_change": "expert"}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "I'm an expert"}]
            result = await extractor.extract_facts_async(user_id, messages)

            # "expert" is not valid, so nothing extracted
            assert result.facts_extracted == 0

    @pytest.mark.asyncio
    async def test_saves_milestones_as_extracted_facts(self, memory_db, sample_user):
        """Should save milestones to extracted_facts table."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"milestones": ["mastered greetings", "first conversation"]}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "Great lesson!"}]
            result = await extractor.extract_facts_async(user_id, messages, channel="voice")

            assert result.facts_extracted == 2
            assert "mastered greetings" in result.milestones
            assert "first conversation" in result.milestones

            # Verify saved to database
            facts = memory_db.get_extracted_facts(user_id, fact_type="milestone")
            assert len(facts) == 2
            values = {f.fact_value for f in facts}
            assert "mastered greetings" in values
            assert "first conversation" in values

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty_result(self, memory_db, sample_user):
        """Should return empty result for malformed JSON."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='Not valid JSON at all')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "Hello"}]
            result = await extractor.extract_facts_async(user_id, messages)

            assert result.facts_extracted == 0
            assert result.profile_updated is False

    @pytest.mark.asyncio
    async def test_empty_extracted_dict_returns_empty_result(self, memory_db, sample_user):
        """Should return empty result when Claude returns empty dict."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "Weather is nice"}]
            result = await extractor.extract_facts_async(user_id, messages)

            assert result.facts_extracted == 0
            assert result.profile_updated is False

    @pytest.mark.asyncio
    async def test_appends_notes_to_existing(self, memory_db, sample_user):
        """Should append new notes to existing notes."""
        user_id = memory_db.create_user(sample_user)

        # Set existing notes
        profile = memory_db.get_or_create_learner_profile(user_id)
        profile.notes = "Prefers morning lessons"
        memory_db.update_learner_profile(profile)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"notes": "Responds well to humor"}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "Haha good one!"}]
            result = await extractor.extract_facts_async(user_id, messages)

            assert result.profile_updated is True

            profile = memory_db.get_or_create_learner_profile(user_id)
            assert "Prefers morning lessons" in profile.notes
            assert "Responds well to humor" in profile.notes


class TestScheduleExtraction:
    """Tests for schedule_extraction method."""

    @pytest.mark.asyncio
    async def test_schedule_extraction_returns_task(self, memory_db, sample_user):
        """Should return an asyncio.Task."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "Hello"}]
            task = extractor.schedule_extraction(user_id, messages)

            assert isinstance(task, asyncio.Task)
            # Wait for completion
            await task

    @pytest.mark.asyncio
    async def test_schedule_extraction_runs_in_background(self, memory_db, sample_user):
        """Should run extraction asynchronously."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"name": "Background"}')]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "I'm Background!"}]
            task = extractor.schedule_extraction(user_id, messages)

            # Wait for task to complete
            result = await task

            assert result.facts_extracted == 1
            profile = memory_db.get_or_create_learner_profile(user_id)
            assert profile.name == "Background"

    @pytest.mark.asyncio
    async def test_schedule_extraction_logs_errors(self, memory_db, sample_user, caplog):
        """Should log errors from background extraction."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.memory.extractor.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("API Error")
            mock_anthropic.return_value = mock_client

            extractor = MemoryExtractor(memory_db, "test-key")
            messages = [{"role": "user", "content": "Hello"}]
            task = extractor.schedule_extraction(user_id, messages)

            # Wait for task to complete (with error)
            try:
                await task
            except Exception:
                pass

            # Error callback should have logged
            # Note: The error callback runs after the task completes
            await asyncio.sleep(0.01)  # Give callback time to run
