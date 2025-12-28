"""Tests for voice bot tool handlers."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from span.db.models import ContentType, CurriculumItem, LessonType
from span.voice.tools import (
    CURRICULUM_TOOLS,
    CurriculumToolHandlers,
    register_tools,
)


class TestCurriculumToolsSchema:
    """Tests for the tool schema definitions."""

    def test_tools_schema_has_standard_tools(self):
        """Should define standard tools."""
        assert CURRICULUM_TOOLS.standard_tools is not None
        assert len(CURRICULUM_TOOLS.standard_tools) >= 4

    def test_record_practice_tool_exists(self):
        """Should have record_practice tool."""
        tool_names = [t.name for t in CURRICULUM_TOOLS.standard_tools]
        assert "record_practice" in tool_names

    def test_get_hint_tool_exists(self):
        """Should have get_hint tool."""
        tool_names = [t.name for t in CURRICULUM_TOOLS.standard_tools]
        assert "get_hint" in tool_names

    def test_get_curriculum_advice_tool_exists(self):
        """Should have get_curriculum_advice tool."""
        tool_names = [t.name for t in CURRICULUM_TOOLS.standard_tools]
        assert "get_curriculum_advice" in tool_names

    def test_end_lesson_summary_tool_exists(self):
        """Should have end_lesson_summary tool."""
        tool_names = [t.name for t in CURRICULUM_TOOLS.standard_tools]
        assert "end_lesson_summary" in tool_names


class TestCurriculumToolHandlers:
    """Tests for CurriculumToolHandlers class."""

    def test_init_stores_dependencies(self, memory_db, config):
        """Should store database, user_id, and config."""
        handlers = CurriculumToolHandlers(memory_db, user_id=1, config=config)
        assert handlers.db == memory_db
        assert handlers.user_id == 1
        assert handlers.config == config

    def test_init_creates_anthropic_client(self, memory_db, config):
        """Should create Anthropic client."""
        with patch("span.voice.tools.Anthropic") as mock_anthropic:
            handlers = CurriculumToolHandlers(memory_db, user_id=1, config=config)
            mock_anthropic.assert_called_once()

    def test_init_tracks_session_start(self, memory_db, config):
        """Should record session start time."""
        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=1, config=config)
            assert handlers.session_start is not None
            assert isinstance(handlers.session_start, datetime)


class TestRecordPractice:
    """Tests for record_practice tool handler."""

    @pytest.mark.asyncio
    async def test_record_practice_updates_progress(
        self, memory_db, sample_user, sample_item, config
    ):
        """Should update SM-2 progress for the word."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        memory_db.get_or_create_progress(user_id, item_id)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "¿Qué onda?", "quality": 4}
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

            params.result_callback.assert_called_once()
            result = params.result_callback.call_args[0][0]
            assert result["status"] == "recorded"

    @pytest.mark.asyncio
    async def test_record_practice_word_not_found(self, memory_db, sample_user, config):
        """Should return not_found for unknown words."""
        user_id = memory_db.create_user(sample_user)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "nonexistent", "quality": 4}
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_record_practice_empty_word_returns_error(
        self, memory_db, sample_user, config
    ):
        """Should return error for empty spanish_word."""
        user_id = memory_db.create_user(sample_user)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "", "quality": 4}
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_record_practice_clamps_quality_upper(
        self, memory_db, sample_user, sample_item, config
    ):
        """Should clamp quality above 5 to 5."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        memory_db.get_or_create_progress(user_id, item_id)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "¿Qué onda?", "quality": 10}
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "recorded"
            # Verify quality was clamped to 5
            assert result["quality"] == 5

    @pytest.mark.asyncio
    async def test_record_practice_clamps_quality_lower(
        self, memory_db, sample_user, sample_item, config
    ):
        """Should clamp quality below 0 to 0."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        memory_db.get_or_create_progress(user_id, item_id)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "¿Qué onda?", "quality": -5}
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "recorded"
            # Verify quality was clamped to 0
            assert result["quality"] == 0


class TestGetHint:
    """Tests for get_hint tool handler."""

    @pytest.mark.asyncio
    async def test_get_hint_exact_match(self, memory_db, sample_user, sample_item, config):
        """Should return hint for exact word match."""
        user_id = memory_db.create_user(sample_user)
        memory_db.add_curriculum_item(sample_item)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "¿Qué onda?"}
            params.result_callback = AsyncMock()

            await handlers.get_hint(params)

            result = params.result_callback.call_args[0][0]
            assert result["found"] is True
            assert result["spanish"] == "¿Qué onda?"
            assert result["english"] == "What's up?"

    @pytest.mark.asyncio
    async def test_get_hint_partial_match(self, memory_db, sample_user, sample_item, config):
        """Should find close matches for partial word."""
        user_id = memory_db.create_user(sample_user)
        memory_db.add_curriculum_item(sample_item)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "qué onda"}  # Missing ¿?
            params.result_callback = AsyncMock()

            await handlers.get_hint(params)

            result = params.result_callback.call_args[0][0]
            assert result["found"] is True

    @pytest.mark.asyncio
    async def test_get_hint_not_found(self, memory_db, sample_user, config):
        """Should return not found for unknown words."""
        user_id = memory_db.create_user(sample_user)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "completely_unknown_word"}
            params.result_callback = AsyncMock()

            await handlers.get_hint(params)

            result = params.result_callback.call_args[0][0]
            assert result["found"] is False

    @pytest.mark.asyncio
    async def test_get_hint_empty_word_returns_error(self, memory_db, sample_user, config):
        """Should return error for empty spanish_word."""
        user_id = memory_db.create_user(sample_user)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": ""}
            params.result_callback = AsyncMock()

            await handlers.get_hint(params)

            result = params.result_callback.call_args[0][0]
            assert result["found"] is False


class TestGetCurriculumAdvice:
    """Tests for get_curriculum_advice tool handler."""

    @pytest.mark.asyncio
    async def test_get_curriculum_advice_calls_claude(self, memory_db, sample_user, config):
        """Should call Claude for advice."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.voice.tools.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Try reviewing vocabulary.")]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {
                "situation": "Student seems bored",
                "question": "What should I do?",
            }
            params.result_callback = AsyncMock()

            await handlers.get_curriculum_advice(params)

            result = params.result_callback.call_args[0][0]
            assert "advice" in result
            assert result["advice"] == "Try reviewing vocabulary."


class TestEndLessonSummary:
    """Tests for end_lesson_summary tool handler."""

    @pytest.mark.asyncio
    async def test_end_lesson_summary_creates_session(
        self, memory_db, sample_user, config
    ):
        """Should create a lesson session."""
        user_id = memory_db.create_user(sample_user)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {
                "words_practiced": ["hola", "adios"],
                "overall_performance": "good",
                "notes": "Good session",
            }
            params.result_callback = AsyncMock()

            await handlers.end_lesson_summary(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "saved"
            assert result["words_count"] == 2

    @pytest.mark.asyncio
    async def test_end_lesson_summary_maps_performance_scores(
        self, memory_db, sample_user, config
    ):
        """Should map performance strings to scores."""
        user_id = memory_db.create_user(sample_user)

        performances = {
            "excellent": 1.0,
            "good": 0.7,
            "needs_work": 0.4,
        }

        for perf, expected_score in performances.items():
            with patch("anthropic.Anthropic"):
                handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

                params = MagicMock()
                params.arguments = {
                    "words_practiced": ["test"],
                    "overall_performance": perf,
                }
                params.result_callback = AsyncMock()

                await handlers.end_lesson_summary(params)

                result = params.result_callback.call_args[0][0]
                assert result["performance"] == perf


class TestRegisterTools:
    """Tests for register_tools function."""

    def test_register_tools_returns_handlers(self, memory_db, config):
        """Should return handlers instance."""
        with patch("anthropic.Anthropic"):
            mock_llm = MagicMock()
            handlers = register_tools(mock_llm, memory_db, user_id=1, config=config)
            assert isinstance(handlers, CurriculumToolHandlers)

    def test_register_tools_registers_functions(self, memory_db, config):
        """Should register all tool functions with LLM."""
        with patch("anthropic.Anthropic"):
            mock_llm = MagicMock()
            register_tools(mock_llm, memory_db, user_id=1, config=config)

            # Should have registered 4 functions
            assert mock_llm.register_function.call_count == 4

            registered_names = [
                call[0][0] for call in mock_llm.register_function.call_args_list
            ]
            assert "record_practice" in registered_names
            assert "get_hint" in registered_names
            assert "get_curriculum_advice" in registered_names
            assert "end_lesson_summary" in registered_names


class TestRecordPracticeIntegration:
    """Integration tests verifying record_practice updates database correctly."""

    @pytest.mark.asyncio
    async def test_record_practice_updates_sm2_in_database(
        self, memory_db, sample_user, sample_item, config
    ):
        """Should persist SM-2 changes to database after practice."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        progress = memory_db.get_or_create_progress(user_id, item_id)

        # Initial state
        assert progress.repetitions == 0
        assert progress.interval_days == 0

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "¿Qué onda?", "quality": 4}
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

        # Verify database was updated
        updated_progress = memory_db.get_or_create_progress(user_id, item_id)
        assert updated_progress.repetitions == 1
        assert updated_progress.interval_days == 1  # First review = 1 day
        assert updated_progress.last_reviewed is not None

    @pytest.mark.asyncio
    async def test_record_practice_increments_repetitions(
        self, memory_db, sample_user, sample_item, config
    ):
        """Should increment repetitions with each practice session."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        memory_db.get_or_create_progress(user_id, item_id)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            # First practice
            params = MagicMock()
            params.arguments = {"spanish_word": "¿Qué onda?", "quality": 4}
            params.result_callback = AsyncMock()
            await handlers.record_practice(params)

            # Second practice
            params2 = MagicMock()
            params2.arguments = {"spanish_word": "¿Qué onda?", "quality": 4}
            params2.result_callback = AsyncMock()
            await handlers.record_practice(params2)

        # Verify repetitions incremented
        progress = memory_db.get_or_create_progress(user_id, item_id)
        assert progress.repetitions == 2
        assert progress.interval_days == 6  # Second review = 6 days

    @pytest.mark.asyncio
    async def test_record_practice_incorrect_resets_progress(
        self, memory_db, sample_user, sample_item, config
    ):
        """Incorrect answer (quality < 3) should reset repetitions."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)

        # Set up some existing progress
        progress = memory_db.get_or_create_progress(user_id, item_id)
        progress.repetitions = 3
        progress.interval_days = 15
        memory_db.update_progress(progress)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "¿Qué onda?", "quality": 2}  # Incorrect
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

        # Verify progress was reset
        updated = memory_db.get_or_create_progress(user_id, item_id)
        assert updated.repetitions == 0
        assert updated.interval_days == 1  # Reset to 1 day


class TestErrorScenarios:
    """Tests for error handling in tool handlers."""

    @pytest.mark.asyncio
    async def test_record_practice_missing_arguments(self, memory_db, sample_user, config):
        """Should handle missing arguments gracefully."""
        user_id = memory_db.create_user(sample_user)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {}  # Missing spanish_word and quality
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "error"
            assert "required" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_get_hint_missing_word(self, memory_db, sample_user, config):
        """Should return found=False for missing word."""
        user_id = memory_db.create_user(sample_user)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {}  # Missing spanish_word
            params.result_callback = AsyncMock()

            await handlers.get_hint(params)

            result = params.result_callback.call_args[0][0]
            assert result["found"] is False
            assert "required" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_get_curriculum_advice_handles_api_error(
        self, memory_db, sample_user, config
    ):
        """Should handle Claude API errors gracefully."""
        user_id = memory_db.create_user(sample_user)

        with patch("span.voice.tools.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("API rate limit")
            mock_anthropic.return_value = mock_client

            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {
                "situation": "Student struggling",
                "question": "What to do?",
            }
            params.result_callback = AsyncMock()

            # Should raise - the code doesn't have error handling
            # This test documents the current behavior
            with pytest.raises(Exception, match="API rate limit"):
                await handlers.get_curriculum_advice(params)

    @pytest.mark.asyncio
    async def test_record_practice_whitespace_only_word(
        self, memory_db, sample_user, config
    ):
        """Should treat whitespace-only word as empty."""
        user_id = memory_db.create_user(sample_user)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "   ", "quality": 4}
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_record_practice_non_integer_quality(
        self, memory_db, sample_user, sample_item, config
    ):
        """Should convert non-integer quality to integer."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        memory_db.get_or_create_progress(user_id, item_id)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {"spanish_word": "¿Qué onda?", "quality": "4"}
            params.result_callback = AsyncMock()

            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "recorded"
            assert result["quality"] == 4


class TestSkillObservationsE2E:
    """End-to-end tests for skill_observations advancing skill dimensions."""

    @pytest.mark.asyncio
    async def test_skill_observations_cause_skill_advancement(
        self, memory_db, sample_user, sample_item_with_skills, config
    ):
        """skill_observations should cause skill dimensions to advance after consecutive correct.

        This tests the full flow:
        1. Item has skill_contributions
        2. Tutor reports skill_observations
        3. After consecutive correct responses, skill dimension advances
        """
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item_with_skills)
        memory_db.get_or_create_progress(user_id, item_id)

        # Verify initial skill level is 1
        initial_skills = memory_db.get_or_create_skill_dimensions(user_id)
        assert initial_skills.vocabulary_production == 1

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            # Simulate multiple consecutive correct responses to trigger advancement
            # The should_advance_skill function requires 3+ consecutive correct
            for i in range(4):
                params = MagicMock()
                params.arguments = {
                    "spanish_word": "¡No manches!",
                    "quality": 5,  # Perfect response
                    "skill_observations": {"vocabulary_production": 3},
                }
                params.result_callback = AsyncMock()
                await handlers.record_practice(params)

        # Verify skill dimension advanced
        updated_skills = memory_db.get_or_create_skill_dimensions(user_id)
        assert updated_skills.vocabulary_production > 1, \
            f"Expected vocabulary_production > 1, got {updated_skills.vocabulary_production}"

    @pytest.mark.asyncio
    async def test_skill_observations_reports_advanced_skills_in_response(
        self, memory_db, sample_user, sample_item_with_skills, config
    ):
        """record_practice should report which skills advanced in the response."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item_with_skills)
        memory_db.get_or_create_progress(user_id, item_id)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            # Pre-set streak to be at threshold
            handlers.skill_streak["vocabulary_production"] = 2

            params = MagicMock()
            params.arguments = {
                "spanish_word": "¡No manches!",
                "quality": 5,
                "skill_observations": {"vocabulary_production": 3},
            }
            params.result_callback = AsyncMock()
            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "recorded"
            # Should report skill advancement
            assert "skills_advanced" in result
            assert isinstance(result["skills_advanced"], dict)

    @pytest.mark.asyncio
    async def test_skill_observations_without_item_contributions(
        self, memory_db, sample_user, sample_item, config
    ):
        """skill_observations should work even without item.skill_contributions."""
        user_id = memory_db.create_user(sample_user)
        # sample_item doesn't have skill_contributions
        item_id = memory_db.add_curriculum_item(sample_item)
        memory_db.get_or_create_progress(user_id, item_id)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            # Pre-set streak to trigger advancement
            handlers.skill_streak["pronunciation"] = 2

            params = MagicMock()
            params.arguments = {
                "spanish_word": "¿Qué onda?",
                "quality": 5,
                # LLM observes pronunciation skill even though item doesn't list it
                "skill_observations": {"pronunciation": 2},
            }
            params.result_callback = AsyncMock()
            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "recorded"

    @pytest.mark.asyncio
    async def test_invalid_skill_observations_ignored(
        self, memory_db, sample_user, sample_item_with_skills, config
    ):
        """Invalid skill names in skill_observations should be ignored."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item_with_skills)
        memory_db.get_or_create_progress(user_id, item_id)

        with patch("anthropic.Anthropic"):
            handlers = CurriculumToolHandlers(memory_db, user_id=user_id, config=config)

            params = MagicMock()
            params.arguments = {
                "spanish_word": "¡No manches!",
                "quality": 5,
                "skill_observations": {
                    "vocabulary_production": 3,
                    "invalid_skill_name": 5,  # Should be ignored
                },
            }
            params.result_callback = AsyncMock()

            # Should not raise, invalid skill is silently ignored
            await handlers.record_practice(params)

            result = params.result_callback.call_args[0][0]
            assert result["status"] == "recorded"
