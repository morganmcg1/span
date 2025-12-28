"""Tests for database models."""

from datetime import datetime

import pytest

from span.db.models import (
    ContentType,
    ConversationMessage,
    CurriculumItem,
    ExtractedFact,
    LearnerProfile,
    LessonSession,
    LessonType,
    User,
    UserProgress,
)


class TestLessonTypeEnum:
    """Tests for LessonType enum."""

    def test_voice_conversation_value(self):
        """Should have voice_conversation value."""
        assert LessonType.VOICE_CONVERSATION.value == "voice_conversation"

    def test_text_vocabulary_value(self):
        """Should have text_vocabulary value."""
        assert LessonType.TEXT_VOCABULARY.value == "text_vocabulary"

    def test_text_practice_value(self):
        """Should have text_practice value."""
        assert LessonType.TEXT_PRACTICE.value == "text_practice"


class TestContentTypeEnum:
    """Tests for ContentType enum."""

    def test_vocabulary_value(self):
        """Should have vocabulary value."""
        assert ContentType.VOCABULARY.value == "vocabulary"

    def test_phrase_value(self):
        """Should have phrase value."""
        assert ContentType.PHRASE.value == "phrase"

    def test_grammar_value(self):
        """Should have grammar value."""
        assert ContentType.GRAMMAR.value == "grammar"

    def test_texting_value(self):
        """Should have texting value."""
        assert ContentType.TEXTING.value == "texting"


class TestUserModel:
    """Tests for User dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        user = User()
        assert user.id is None
        assert user.phone_number == ""
        assert user.telegram_id == 0
        assert user.timezone == "Europe/Dublin"
        assert user.preferred_call_times == '["09:50"]'
        assert user.created_at is None

    def test_custom_values(self):
        """Should store custom values."""
        user = User(
            id=1,
            phone_number="+1234567890",
            telegram_id=123456,
            timezone="America/Mexico_City",
        )
        assert user.id == 1
        assert user.phone_number == "+1234567890"
        assert user.telegram_id == 123456
        assert user.timezone == "America/Mexico_City"


class TestCurriculumItemModel:
    """Tests for CurriculumItem dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        item = CurriculumItem()
        assert item.id is None
        assert item.content_type == ContentType.VOCABULARY
        assert item.spanish == ""
        assert item.english == ""
        assert item.example_sentence is None
        assert item.mexican_notes is None
        assert item.topic == ""
        assert item.difficulty == 1

    def test_custom_values(self):
        """Should store custom values."""
        item = CurriculumItem(
            content_type=ContentType.PHRASE,
            spanish="¿Qué onda?",
            english="What's up?",
            topic="greetings",
            difficulty=2,
        )
        assert item.content_type == ContentType.PHRASE
        assert item.spanish == "¿Qué onda?"
        assert item.english == "What's up?"
        assert item.topic == "greetings"
        assert item.difficulty == 2


class TestUserProgressModel:
    """Tests for UserProgress dataclass."""

    def test_default_values(self):
        """Should have SM-2 defaults."""
        progress = UserProgress()
        assert progress.id is None
        assert progress.user_id == 0
        assert progress.item_id == 0
        assert progress.easiness_factor == 2.5
        assert progress.interval_days == 0
        assert progress.repetitions == 0
        assert progress.next_review is None
        assert progress.last_reviewed is None


class TestLessonSessionModel:
    """Tests for LessonSession dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        session = LessonSession()
        assert session.id is None
        assert session.user_id == 0
        assert session.lesson_type == LessonType.VOICE_CONVERSATION
        assert session.topic == ""
        assert session.items_covered == "[]"
        assert session.performance_score is None
        assert session.duration_seconds is None


class TestConversationMessageModel:
    """Tests for ConversationMessage dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        msg = ConversationMessage()
        assert msg.id is None
        assert msg.user_id == 0
        assert msg.session_id is None
        assert msg.role == "user"
        assert msg.content == ""
        assert msg.channel == "telegram"
        assert msg.audio_path is None

    def test_custom_values(self):
        """Should store custom values."""
        msg = ConversationMessage(
            role="assistant",
            content="¡Hola!",
            channel="voice",
            audio_path="/path/to/audio.ogg",
        )
        assert msg.role == "assistant"
        assert msg.content == "¡Hola!"
        assert msg.channel == "voice"
        assert msg.audio_path == "/path/to/audio.ogg"


class TestLearnerProfileModel:
    """Tests for LearnerProfile dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        profile = LearnerProfile()
        assert profile.id is None
        assert profile.user_id == 0
        assert profile.name is None
        assert profile.native_language == "English"
        assert profile.location is None
        assert profile.level == "beginner"
        assert profile.strong_topics == []
        assert profile.weak_topics == []
        assert profile.interests == []
        assert profile.goals == []
        assert profile.conversation_style == "casual"
        assert profile.notes is None

    def test_list_defaults_are_independent(self):
        """List fields should be independent across instances."""
        p1 = LearnerProfile()
        p2 = LearnerProfile()
        p1.interests.append("music")
        assert "music" in p1.interests
        assert "music" not in p2.interests


class TestLearnerProfileToContextBlock:
    """Tests for LearnerProfile.to_context_block method."""

    def test_minimal_profile(self):
        """Should include level and native language for minimal profile."""
        profile = LearnerProfile(user_id=1)
        context = profile.to_context_block()

        assert "Level: beginner" in context
        assert "Native language: English" in context
        assert "casual conversation style" in context

    def test_full_profile(self):
        """Should include all fields when populated."""
        profile = LearnerProfile(
            user_id=1,
            name="Carlos",
            location="Mexico City",
            level="intermediate",
            native_language="Spanish",
            strong_topics=["greetings", "food"],
            weak_topics=["subjunctive"],
            interests=["music", "travel"],
            goals=["conversational fluency"],
            conversation_style="immersive",
            notes="Prefers morning lessons",
        )
        context = profile.to_context_block()

        assert "Name: Carlos" in context
        assert "From: Mexico City" in context
        assert "Level: intermediate" in context
        assert "Native language: Spanish" in context
        assert "Strong at: greetings, food" in context
        assert "Needs work on: subjunctive" in context
        assert "Interests: music, travel" in context
        assert "Goals: conversational fluency" in context
        assert "Prefers: immersive conversation style" in context
        assert "Notes: Prefers morning lessons" in context

    def test_omits_empty_name(self):
        """Should not include name line if None."""
        profile = LearnerProfile(user_id=1, name=None)
        context = profile.to_context_block()
        assert "Name:" not in context

    def test_omits_empty_location(self):
        """Should not include location line if None."""
        profile = LearnerProfile(user_id=1, location=None)
        context = profile.to_context_block()
        assert "From:" not in context

    def test_omits_empty_strong_topics(self):
        """Should not include strong topics if empty."""
        profile = LearnerProfile(user_id=1, strong_topics=[])
        context = profile.to_context_block()
        assert "Strong at:" not in context

    def test_omits_empty_weak_topics(self):
        """Should not include weak topics if empty."""
        profile = LearnerProfile(user_id=1, weak_topics=[])
        context = profile.to_context_block()
        assert "Needs work on:" not in context

    def test_omits_empty_interests(self):
        """Should not include interests if empty."""
        profile = LearnerProfile(user_id=1, interests=[])
        context = profile.to_context_block()
        assert "Interests:" not in context

    def test_omits_empty_goals(self):
        """Should not include goals if empty."""
        profile = LearnerProfile(user_id=1, goals=[])
        context = profile.to_context_block()
        assert "Goals:" not in context

    def test_omits_empty_notes(self):
        """Should not include notes if None."""
        profile = LearnerProfile(user_id=1, notes=None)
        context = profile.to_context_block()
        assert "Notes:" not in context


class TestExtractedFactModel:
    """Tests for ExtractedFact dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        fact = ExtractedFact()
        assert fact.id is None
        assert fact.user_id == 0
        assert fact.fact_type == ""
        assert fact.fact_value == ""
        assert fact.source_channel is None
        assert fact.confidence == 1.0
        assert fact.created_at is None

    def test_custom_values(self):
        """Should store custom values."""
        fact = ExtractedFact(
            user_id=1,
            fact_type="interest",
            fact_value="music",
            source_channel="telegram",
            confidence=0.9,
        )
        assert fact.user_id == 1
        assert fact.fact_type == "interest"
        assert fact.fact_value == "music"
        assert fact.source_channel == "telegram"
        assert fact.confidence == 0.9
