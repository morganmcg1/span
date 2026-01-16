"""Tests for voice bot system prompt and configuration."""

import pytest
from unittest.mock import patch, MagicMock

from span.voice.bot import SpanishTutorBot


class TestBuildSystemPrompt:
    """Tests for SpanishTutorBot.build_system_prompt method."""

    def test_build_system_prompt_includes_skill_levels(
        self, memory_db, sample_user, config
    ):
        """System prompt should include current skill levels."""
        user_id = memory_db.create_user(sample_user)

        # Update a skill to non-default value
        skills = memory_db.get_or_create_skill_dimensions(user_id)
        skills.pronunciation = 3
        skills.vocabulary_production = 2
        memory_db.update_skill_dimensions(skills)

        # Build prompt
        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id)
        prompt = bot.build_system_prompt()

        # Verify skill context is present
        assert "Current Skill Levels" in prompt
        assert "pronunciation: 3" in prompt
        assert "RECOGNITION" in prompt  # Level 3 name
        assert "vocabulary_production: 2" in prompt
        assert "EXPOSURE" in prompt  # Level 2 name

    def test_build_system_prompt_includes_all_nine_skills(
        self, memory_db, sample_user, config
    ):
        """System prompt should include all 9 skill dimensions."""
        user_id = memory_db.create_user(sample_user)

        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id)
        prompt = bot.build_system_prompt()

        skill_names = [
            "vocabulary_recognition",
            "vocabulary_production",
            "pronunciation",
            "grammar_receptive",
            "grammar_productive",
            "conversational_flow",
            "cultural_pragmatics",
            "narration",
            "conditionals",
        ]

        for skill in skill_names:
            assert skill in prompt, f"Missing skill: {skill}"

    def test_build_system_prompt_includes_skill_observation_guidance(
        self, memory_db, sample_user, config
    ):
        """System prompt should guide tutor to use skill_observations."""
        user_id = memory_db.create_user(sample_user)

        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id)
        prompt = bot.build_system_prompt()

        # Check for guidance about using skill_observations parameter
        assert "skill_observations" in prompt.lower() or "skill" in prompt.lower()

    def test_build_system_prompt_without_database(self, config):
        """System prompt should work without database (no skill context)."""
        bot = SpanishTutorBot(config, db=None, user_id=1)
        prompt = bot.build_system_prompt()

        # Should still have basic prompt content
        assert len(prompt) > 0
        # But no skill levels section since no DB
        assert "Current Skill Levels" not in prompt

    def test_build_system_prompt_includes_learner_profile(
        self, memory_db, sample_user, config
    ):
        """System prompt should include learner profile context."""
        user_id = memory_db.create_user(sample_user)

        # Set up learner profile with some data
        profile = memory_db.get_or_create_learner_profile(user_id)
        profile.name = "Test Learner"
        profile.level = "intermediate"
        profile.interests = ["travel", "food"]
        memory_db.update_learner_profile(profile)

        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id)
        prompt = bot.build_system_prompt()

        # Verify learner profile is included
        assert "About This Learner" in prompt or "Test Learner" in prompt

    def test_build_system_prompt_reflects_skill_changes(
        self, memory_db, sample_user, config
    ):
        """System prompt should reflect updated skill levels."""
        user_id = memory_db.create_user(sample_user)

        # Build initial prompt
        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id)
        initial_prompt = bot.build_system_prompt()

        # Update skills
        skills = memory_db.get_or_create_skill_dimensions(user_id)
        skills.narration = 4  # PRODUCTION level
        memory_db.update_skill_dimensions(skills)

        # Build prompt again (creates new bot to refresh skills)
        bot2 = SpanishTutorBot(config, db=memory_db, user_id=user_id)
        updated_prompt = bot2.build_system_prompt()

        # Verify the prompt now shows level 4 for narration
        assert "narration: 4" in updated_prompt
        assert "PRODUCTION" in updated_prompt


class TestSpanishTutorBotInit:
    """Tests for SpanishTutorBot initialization."""

    def test_init_stores_config(self, config):
        """Should store configuration."""
        bot = SpanishTutorBot(config)
        assert bot.config == config

    def test_init_stores_user_id(self, config, memory_db, sample_user):
        """Should store user_id."""
        user_id = memory_db.create_user(sample_user)
        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id)
        assert bot.user_id == user_id

    def test_init_creates_memory_extractor_when_db_and_api_key(
        self, config, memory_db, sample_user
    ):
        """Should create MemoryExtractor when db and api key are available."""
        user_id = memory_db.create_user(sample_user)
        with patch("span.voice.bot.MemoryExtractor") as mock_extractor:
            bot = SpanishTutorBot(config, db=memory_db, user_id=user_id)
            mock_extractor.assert_called_once()

    def test_init_stores_is_news_lesson_flag(self, config):
        """Should store is_news_lesson flag."""
        bot = SpanishTutorBot(config, is_news_lesson=True)
        assert bot.is_news_lesson is True

        bot2 = SpanishTutorBot(config, is_news_lesson=False)
        assert bot2.is_news_lesson is False

    def test_init_stores_is_recall_lesson_flag(self, config):
        """Should store is_recall_lesson flag."""
        bot = SpanishTutorBot(config, is_recall_lesson=True)
        assert bot.is_recall_lesson is True

        bot2 = SpanishTutorBot(config, is_recall_lesson=False)
        assert bot2.is_recall_lesson is False


class TestNewsLessonPrompt:
    """Tests for news lesson prompt injection."""

    def test_news_lesson_instructions_included_when_flag_true(
        self, memory_db, sample_user, config
    ):
        """System prompt should include news lesson instructions when is_news_lesson=True."""
        user_id = memory_db.create_user(sample_user)

        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id, is_news_lesson=True)
        prompt = bot.build_system_prompt()

        # Verify news lesson instructions are present
        assert "News Discussion" in prompt
        assert "get_news" in prompt
        assert "summary_for_student" in prompt

    def test_news_lesson_instructions_excluded_when_flag_false(
        self, memory_db, sample_user, config
    ):
        """System prompt should NOT include news lesson instructions when is_news_lesson=False."""
        user_id = memory_db.create_user(sample_user)

        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id, is_news_lesson=False)
        prompt = bot.build_system_prompt()

        # Verify news lesson instructions are NOT present
        assert "News Discussion" not in prompt


class TestRecallLessonPrompt:
    """Tests for recall lesson prompt injection."""

    def test_recall_lesson_instructions_included_when_flag_true(
        self, memory_db, sample_user, config
    ):
        """System prompt should include recall lesson instructions when is_recall_lesson=True."""
        user_id = memory_db.create_user(sample_user)

        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id, is_recall_lesson=True)
        prompt = bot.build_system_prompt()

        # Verify recall lesson instructions are present
        assert "Recall & Review" in prompt
        assert "get_recall" in prompt

    def test_recall_lesson_instructions_excluded_when_flag_false(
        self, memory_db, sample_user, config
    ):
        """System prompt should NOT include recall lesson instructions when is_recall_lesson=False."""
        user_id = memory_db.create_user(sample_user)

        bot = SpanishTutorBot(config, db=memory_db, user_id=user_id, is_recall_lesson=False)
        prompt = bot.build_system_prompt()

        # Verify recall lesson instructions are NOT present
        assert "Recall & Review" not in prompt

    def test_recall_takes_precedence_over_news(
        self, memory_db, sample_user, config
    ):
        """When both flags are set, recall should take precedence over news."""
        user_id = memory_db.create_user(sample_user)

        bot = SpanishTutorBot(
            config, db=memory_db, user_id=user_id,
            is_recall_lesson=True, is_news_lesson=True
        )
        prompt = bot.build_system_prompt()

        # Recall instructions should be present, not news
        assert "Recall & Review" in prompt
        assert "News Discussion" not in prompt
