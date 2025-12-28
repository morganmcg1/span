"""Tests for database operations."""

import json
from datetime import datetime, timedelta

import pytest

from span.db.database import Database
from span.db.models import (
    ContentType,
    CurriculumItem,
    LearnerProfile,
    LessonSession,
    LessonType,
    User,
)


class TestUserOperations:
    """Tests for user CRUD operations."""

    def test_create_user(self, memory_db, sample_user):
        """Creating a user should return its ID."""
        user_id = memory_db.create_user(sample_user)
        assert user_id == 1

    def test_create_multiple_users(self, memory_db, sample_user):
        """Multiple users should get sequential IDs."""
        id1 = memory_db.create_user(sample_user)
        sample_user.telegram_id = 999999
        id2 = memory_db.create_user(sample_user)
        assert id1 == 1
        assert id2 == 2

    def test_get_user(self, memory_db, sample_user):
        """Should retrieve a user by ID."""
        user_id = memory_db.create_user(sample_user)
        retrieved = memory_db.get_user(user_id)
        assert retrieved is not None
        assert retrieved.phone_number == sample_user.phone_number
        assert retrieved.telegram_id == sample_user.telegram_id
        assert retrieved.timezone == sample_user.timezone

    def test_get_user_not_found(self, memory_db):
        """Should return None for non-existent user."""
        assert memory_db.get_user(999) is None

    def test_get_user_by_telegram(self, memory_db, sample_user):
        """Should retrieve a user by Telegram ID."""
        memory_db.create_user(sample_user)
        retrieved = memory_db.get_user_by_telegram(sample_user.telegram_id)
        assert retrieved is not None
        assert retrieved.telegram_id == sample_user.telegram_id

    def test_get_user_by_telegram_not_found(self, memory_db):
        """Should return None for non-existent Telegram ID."""
        assert memory_db.get_user_by_telegram(999) is None


class TestCurriculumOperations:
    """Tests for curriculum item operations."""

    def test_add_curriculum_item(self, memory_db, sample_item):
        """Adding a curriculum item should return its ID."""
        item_id = memory_db.add_curriculum_item(sample_item)
        assert item_id == 1

    def test_get_curriculum_item(self, memory_db, sample_item):
        """Should retrieve a curriculum item by ID."""
        item_id = memory_db.add_curriculum_item(sample_item)
        retrieved = memory_db.get_curriculum_item(item_id)
        assert retrieved is not None
        assert retrieved.spanish == sample_item.spanish
        assert retrieved.english == sample_item.english
        assert retrieved.topic == sample_item.topic
        assert retrieved.content_type == sample_item.content_type

    def test_get_curriculum_item_not_found(self, memory_db):
        """Should return None for non-existent item."""
        assert memory_db.get_curriculum_item(999) is None

    def test_get_all_curriculum_items(self, memory_db, sample_item, sample_vocabulary_item):
        """Should return all curriculum items sorted by difficulty."""
        memory_db.add_curriculum_item(sample_vocabulary_item)  # difficulty 2
        memory_db.add_curriculum_item(sample_item)  # difficulty 1
        items = memory_db.get_all_curriculum_items()
        assert len(items) == 2
        assert items[0].difficulty <= items[1].difficulty

    def test_get_all_curriculum_items_empty(self, memory_db):
        """Should return empty list when no items exist."""
        items = memory_db.get_all_curriculum_items()
        assert items == []

    def test_get_curriculum_items_by_topic(self, memory_db, sample_item, sample_vocabulary_item):
        """Should filter items by topic."""
        memory_db.add_curriculum_item(sample_item)  # greetings
        memory_db.add_curriculum_item(sample_vocabulary_item)  # food
        greetings = memory_db.get_curriculum_items_by_topic("greetings")
        assert len(greetings) == 1
        assert greetings[0].spanish == sample_item.spanish

    def test_get_curriculum_item_by_spanish(self, memory_db, sample_item):
        """Should find item by Spanish text."""
        memory_db.add_curriculum_item(sample_item)
        found = memory_db.get_curriculum_item_by_spanish("¿Qué onda?")
        assert found is not None
        assert found.english == sample_item.english

    def test_get_curriculum_item_by_spanish_case_insensitive(self, memory_db, sample_item):
        """Spanish lookup should be case-insensitive."""
        memory_db.add_curriculum_item(sample_item)
        found = memory_db.get_curriculum_item_by_spanish("¿qué onda?")
        assert found is not None

    def test_get_curriculum_item_by_spanish_not_found(self, memory_db):
        """Should return None when Spanish text not found."""
        assert memory_db.get_curriculum_item_by_spanish("nonexistent") is None

    def test_get_user_vocabulary(self, populated_db):
        """Should return items the user is learning."""
        vocab = populated_db.get_user_vocabulary(user_id=1, limit=10)
        assert len(vocab) == 1  # Only one item has progress

    def test_get_user_vocabulary_empty(self, memory_db, sample_user):
        """Should return empty list when user has no progress."""
        user_id = memory_db.create_user(sample_user)
        vocab = memory_db.get_user_vocabulary(user_id)
        assert vocab == []


class TestProgressOperations:
    """Tests for user progress operations."""

    def test_get_or_create_progress_creates(self, memory_db, sample_user, sample_item):
        """Should create progress when it doesn't exist."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        progress = memory_db.get_or_create_progress(user_id, item_id)
        assert progress.user_id == user_id
        assert progress.item_id == item_id
        assert progress.easiness_factor == 2.5
        assert progress.repetitions == 0

    def test_get_or_create_progress_returns_existing(self, memory_db, sample_user, sample_item):
        """Should return existing progress instead of creating."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        p1 = memory_db.get_or_create_progress(user_id, item_id)
        p2 = memory_db.get_or_create_progress(user_id, item_id)
        assert p1.id == p2.id

    def test_update_progress(self, memory_db, sample_user, sample_item):
        """Should update progress fields."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        progress = memory_db.get_or_create_progress(user_id, item_id)

        # Update
        progress.easiness_factor = 2.8
        progress.interval_days = 6
        progress.repetitions = 2
        progress.next_review = datetime.now() + timedelta(days=6)
        progress.last_reviewed = datetime.now()
        memory_db.update_progress(progress)

        # Retrieve again
        updated = memory_db.get_or_create_progress(user_id, item_id)
        assert updated.easiness_factor == 2.8
        assert updated.interval_days == 6
        assert updated.repetitions == 2

    def test_get_items_due_for_review(self, memory_db, sample_user, sample_item):
        """Should return items with past due dates."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        progress = memory_db.get_or_create_progress(user_id, item_id)

        # Set next_review to past
        progress.next_review = datetime.now() - timedelta(hours=1)
        memory_db.update_progress(progress)

        due = memory_db.get_items_due_for_review(user_id)
        assert len(due) == 1
        assert due[0].spanish == sample_item.spanish

    def test_get_items_due_for_review_excludes_future(self, memory_db, sample_user, sample_item):
        """Should not return items scheduled for the future."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)
        progress = memory_db.get_or_create_progress(user_id, item_id)

        # Set next_review to future
        progress.next_review = datetime.now() + timedelta(days=7)
        memory_db.update_progress(progress)

        due = memory_db.get_items_due_for_review(user_id)
        assert len(due) == 0

    def test_get_new_items_for_user(self, memory_db, sample_user, sample_item, sample_vocabulary_item):
        """Should return items without progress."""
        user_id = memory_db.create_user(sample_user)
        item1_id = memory_db.add_curriculum_item(sample_item)
        memory_db.add_curriculum_item(sample_vocabulary_item)

        # Create progress only for item1
        memory_db.get_or_create_progress(user_id, item1_id)

        new_items = memory_db.get_new_items_for_user(user_id)
        assert len(new_items) == 1
        assert new_items[0].spanish == sample_vocabulary_item.spanish


class TestSessionOperations:
    """Tests for lesson session operations."""

    def test_create_session(self, memory_db, sample_user, sample_session):
        """Should create a session and return its ID."""
        user_id = memory_db.create_user(sample_user)
        sample_session.user_id = user_id
        session_id = memory_db.create_session(sample_session)
        assert session_id == 1

    def test_get_recent_sessions(self, memory_db, sample_user, sample_session):
        """Should return recent sessions."""
        user_id = memory_db.create_user(sample_user)
        sample_session.user_id = user_id

        # Create multiple sessions
        memory_db.create_session(sample_session)
        sample_session.topic = "food"
        memory_db.create_session(sample_session)

        sessions = memory_db.get_recent_sessions(user_id, limit=10)
        assert len(sessions) == 2
        # Both sessions should be present
        topics = {s.topic for s in sessions}
        assert "greetings" in topics
        assert "food" in topics

    def test_get_recent_sessions_respects_limit(self, memory_db, sample_user, sample_session):
        """Should respect the limit parameter."""
        user_id = memory_db.create_user(sample_user)
        sample_session.user_id = user_id

        # Create 5 sessions
        for i in range(5):
            sample_session.topic = f"topic_{i}"
            memory_db.create_session(sample_session)

        sessions = memory_db.get_recent_sessions(user_id, limit=3)
        assert len(sessions) == 3


class TestMessageOperations:
    """Tests for conversation message operations."""

    def test_save_message(self, memory_db, sample_user):
        """Should save a message and return its ID."""
        user_id = memory_db.create_user(sample_user)
        msg_id = memory_db.save_message(user_id, "user", "Hola", "telegram")
        assert msg_id == 1

    def test_save_message_with_audio_path(self, memory_db, sample_user):
        """Should save message with audio path."""
        user_id = memory_db.create_user(sample_user)
        msg_id = memory_db.save_message(
            user_id, "user", "Hola", "telegram_voice",
            audio_path="/path/to/audio.ogg"
        )
        history = memory_db.get_conversation_history(user_id)
        assert len(history) == 1
        assert history[0].audio_path == "/path/to/audio.ogg"

    def test_get_conversation_history(self, memory_db, sample_user):
        """Should return messages."""
        user_id = memory_db.create_user(sample_user)
        memory_db.save_message(user_id, "user", "Hola", "telegram")
        memory_db.save_message(user_id, "assistant", "¡Hola! ¿Cómo estás?", "telegram")

        history = memory_db.get_conversation_history(user_id)
        assert len(history) == 2
        # Both messages should be present
        contents = {m.content for m in history}
        assert "Hola" in contents
        assert "¡Hola! ¿Cómo estás?" in contents

    def test_get_conversation_history_filters_by_channel(self, memory_db, sample_user):
        """Should filter by channel when specified."""
        user_id = memory_db.create_user(sample_user)
        memory_db.save_message(user_id, "user", "Telegram msg", "telegram")
        memory_db.save_message(user_id, "user", "Voice msg", "voice")

        telegram_only = memory_db.get_conversation_history(user_id, channel="telegram")
        assert len(telegram_only) == 1
        assert telegram_only[0].content == "Telegram msg"

    def test_get_conversation_history_respects_limit(self, memory_db, sample_user):
        """Should respect limit parameter."""
        user_id = memory_db.create_user(sample_user)
        for i in range(10):
            memory_db.save_message(user_id, "user", f"Message {i}", "telegram")

        history = memory_db.get_conversation_history(user_id, limit=3)
        assert len(history) == 3
        # All returned messages should be from our set
        for msg in history:
            assert msg.content.startswith("Message ")


class TestLearnerProfileOperations:
    """Tests for learner profile operations."""

    def test_get_or_create_profile_creates(self, memory_db, sample_user):
        """Should create profile when it doesn't exist."""
        user_id = memory_db.create_user(sample_user)
        profile = memory_db.get_or_create_learner_profile(user_id)
        assert profile.user_id == user_id
        assert profile.level == "beginner"  # default

    def test_get_or_create_profile_returns_existing(self, memory_db, sample_user):
        """Should return existing profile."""
        user_id = memory_db.create_user(sample_user)
        p1 = memory_db.get_or_create_learner_profile(user_id)
        p2 = memory_db.get_or_create_learner_profile(user_id)
        # Should be same profile (though IDs might not be set)
        assert p1.user_id == p2.user_id

    def test_update_learner_profile(self, memory_db, sample_user):
        """Should update profile fields including JSON lists."""
        user_id = memory_db.create_user(sample_user)
        profile = memory_db.get_or_create_learner_profile(user_id)

        # Update
        profile.name = "Morgan"
        profile.level = "intermediate"
        profile.interests = ["music", "travel"]
        profile.goals = ["conversational fluency"]
        memory_db.update_learner_profile(profile)

        # Retrieve again
        updated = memory_db.get_or_create_learner_profile(user_id)
        assert updated.name == "Morgan"
        assert updated.level == "intermediate"
        assert updated.interests == ["music", "travel"]
        assert updated.goals == ["conversational fluency"]


class TestExtractedFactsOperations:
    """Tests for extracted facts operations."""

    def test_save_extracted_fact(self, memory_db, sample_user):
        """Should save a fact and return its ID."""
        user_id = memory_db.create_user(sample_user)
        fact_id = memory_db.save_extracted_fact(
            user_id, "interest", "music", "telegram", 0.9
        )
        assert fact_id == 1

    def test_get_extracted_facts(self, memory_db, sample_user):
        """Should retrieve all facts for a user."""
        user_id = memory_db.create_user(sample_user)
        memory_db.save_extracted_fact(user_id, "interest", "music", "telegram")
        memory_db.save_extracted_fact(user_id, "location", "Ireland", "voice")

        facts = memory_db.get_extracted_facts(user_id)
        assert len(facts) == 2

    def test_get_extracted_facts_filters_by_type(self, memory_db, sample_user):
        """Should filter facts by type."""
        user_id = memory_db.create_user(sample_user)
        memory_db.save_extracted_fact(user_id, "interest", "music", "telegram")
        memory_db.save_extracted_fact(user_id, "interest", "travel", "telegram")
        memory_db.save_extracted_fact(user_id, "location", "Ireland", "voice")

        interests = memory_db.get_extracted_facts(user_id, fact_type="interest")
        assert len(interests) == 2
        assert all(f.fact_type == "interest" for f in interests)

    def test_get_extracted_facts_respects_limit(self, memory_db, sample_user):
        """Should respect limit parameter."""
        user_id = memory_db.create_user(sample_user)
        for i in range(10):
            memory_db.save_extracted_fact(user_id, "interest", f"interest_{i}")

        facts = memory_db.get_extracted_facts(user_id, limit=5)
        assert len(facts) == 5


class TestDatabaseMigration:
    """Tests for database migration handling."""

    def test_init_schema_is_idempotent(self, memory_db):
        """init_schema should be safe to call multiple times."""
        # First call already happened in fixture
        # Call again - should not raise
        memory_db.init_schema()
        memory_db.init_schema()

        # Verify database still works
        with memory_db.connection() as conn:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert users >= 0

    def test_skill_dimensions_table_exists(self, memory_db):
        """skill_dimensions table should be created by init_schema."""
        # Check table exists
        with memory_db.connection() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_dimensions'"
            ).fetchone()
        assert result is not None
        assert result[0] == "skill_dimensions"

    def test_curriculum_items_has_new_columns(self, memory_db):
        """curriculum_items should have adaptive selection columns."""
        # Get column info
        with memory_db.connection() as conn:
            columns = conn.execute("PRAGMA table_info(curriculum_items)").fetchall()
        column_names = {col[1] for col in columns}

        # Check for new columns
        expected_columns = {
            "skill_requirements",
            "skill_contributions",
            "cefr_level",
            "prompt_types",
            "prerequisite_items",
        }
        for col in expected_columns:
            assert col in column_names, f"Missing column: {col}"

    def test_migration_adds_missing_columns(self, tmp_path):
        """Migration should add missing columns to existing tables."""
        from span.db.database import Database

        db_path = tmp_path / "test_migration.db"

        # Create a minimal database without new columns
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE curriculum_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT,
                spanish TEXT,
                english TEXT,
                topic TEXT,
                difficulty INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            INSERT INTO curriculum_items (content_type, spanish, english, topic, difficulty)
            VALUES ('phrase', 'hola', 'hello', 'greetings', 1)
        """)
        conn.commit()
        conn.close()

        # Now open with our Database class - should migrate
        db = Database(str(db_path))
        db.init_schema()

        # Check that new columns were added
        with db.connection() as conn:
            columns = conn.execute("PRAGMA table_info(curriculum_items)").fetchall()
            column_names = {col[1] for col in columns}

            assert "skill_requirements" in column_names
            assert "skill_contributions" in column_names
            assert "cefr_level" in column_names

            # Check that existing data is preserved
            item = conn.execute("SELECT spanish FROM curriculum_items WHERE id=1").fetchone()
            assert item[0] == "hola"

    def test_skill_dimensions_crud(self, memory_db, sample_user):
        """Skill dimensions should be creatable and updatable."""
        user_id = memory_db.create_user(sample_user)

        # Get or create should create with defaults
        skills = memory_db.get_or_create_skill_dimensions(user_id)
        assert skills.user_id == user_id
        assert skills.vocabulary_recognition == 1  # Default
        assert skills.narration == 1  # Default

        # Update a skill
        skills.vocabulary_production = 3
        skills.narration = 2
        memory_db.update_skill_dimensions(skills)

        # Retrieve and verify
        updated = memory_db.get_or_create_skill_dimensions(user_id)
        assert updated.vocabulary_production == 3
        assert updated.narration == 2
