"""Tests for curriculum scheduling and daily plan generation."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from span.curriculum.scheduler import CurriculumScheduler, DailyPlan
from span.db.models import ContentType, CurriculumItem


class TestDailyPlanDataclass:
    """Tests for the DailyPlan dataclass."""

    def test_daily_plan_creation(self):
        """DailyPlan should store all fields."""
        plan = DailyPlan(
            review_items=[],
            new_items=[],
            suggested_topic="greetings",
            voice_lesson_focus="Review: hola",
            telegram_exercises=[],
            interleaved_topics=["greetings", "expressions"],
        )
        assert plan.suggested_topic == "greetings"
        assert plan.voice_lesson_focus == "Review: hola"
        assert plan.interleaved_topics == ["greetings", "expressions"]


class TestCurriculumScheduler:
    """Tests for CurriculumScheduler."""

    def test_init_stores_db(self, memory_db):
        """Scheduler should store database reference."""
        scheduler = CurriculumScheduler(memory_db)
        assert scheduler.db == memory_db

    def test_get_items_due_for_review_delegates_to_db(self, memory_db, sample_user, sample_item):
        """get_items_due_for_review should delegate to database."""
        user_id = memory_db.create_user(sample_user)
        item_id = memory_db.add_curriculum_item(sample_item)

        # Create progress with past due date
        progress = memory_db.get_or_create_progress(user_id, item_id)
        progress.next_review = datetime.now() - timedelta(hours=1)
        memory_db.update_progress(progress)

        scheduler = CurriculumScheduler(memory_db)
        due_items = scheduler.get_items_due_for_review(user_id)
        assert len(due_items) == 1

    def test_get_new_items_delegates_to_db(self, memory_db, sample_user, sample_item):
        """get_new_items should delegate to database."""
        user_id = memory_db.create_user(sample_user)
        memory_db.add_curriculum_item(sample_item)

        scheduler = CurriculumScheduler(memory_db)
        new_items = scheduler.get_new_items(user_id)
        assert len(new_items) == 1


class TestCreateDailyPlan:
    """Tests for create_daily_plan method."""

    def test_create_daily_plan_with_review_and_new_items(
        self, memory_db, sample_user, sample_item, sample_vocabulary_item
    ):
        """Plan should include both review and new items."""
        user_id = memory_db.create_user(sample_user)

        # Add two items
        item1_id = memory_db.add_curriculum_item(sample_item)
        memory_db.add_curriculum_item(sample_vocabulary_item)

        # Create progress for item1 with past due date
        progress = memory_db.get_or_create_progress(user_id, item1_id)
        progress.next_review = datetime.now() - timedelta(hours=1)
        memory_db.update_progress(progress)

        scheduler = CurriculumScheduler(memory_db)
        plan = scheduler.create_daily_plan(user_id)

        assert len(plan.review_items) == 1
        assert len(plan.new_items) == 1

    def test_create_daily_plan_with_only_new_items(self, memory_db, sample_user, sample_item):
        """Plan should work with only new items."""
        user_id = memory_db.create_user(sample_user)
        memory_db.add_curriculum_item(sample_item)

        scheduler = CurriculumScheduler(memory_db)
        plan = scheduler.create_daily_plan(user_id)

        assert len(plan.review_items) == 0
        assert len(plan.new_items) == 1

    def test_create_daily_plan_empty_curriculum(self, memory_db, sample_user):
        """Plan should handle empty curriculum gracefully."""
        user_id = memory_db.create_user(sample_user)

        scheduler = CurriculumScheduler(memory_db)
        plan = scheduler.create_daily_plan(user_id)

        assert len(plan.review_items) == 0
        assert len(plan.new_items) == 0
        assert plan.suggested_topic == "general conversation"
        assert plan.voice_lesson_focus == "Free conversation practice"


class TestPickTopic:
    """Tests for _pick_topic method."""

    def test_pick_topic_with_single_topic(self):
        """Should return the only topic when all items share it."""
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
        scheduler = CurriculumScheduler(MagicMock())
        topic = scheduler._pick_topic(items, [])
        assert topic == "greetings"

    def test_pick_topic_returns_most_common(self):
        """Should return the most common topic."""
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
                spanish="chela",
                english="beer",
                topic="food",
                difficulty=1,
            ),
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="tacos",
                english="tacos",
                topic="food",
                difficulty=1,
            ),
        ]
        scheduler = CurriculumScheduler(MagicMock())
        topic = scheduler._pick_topic(items, [])
        assert topic == "food"

    def test_pick_topic_empty_returns_default(self):
        """Should return 'general conversation' when no items."""
        scheduler = CurriculumScheduler(MagicMock())
        topic = scheduler._pick_topic([], [])
        assert topic == "general conversation"

    def test_pick_topic_combines_review_and_new(self):
        """Should consider both review and new items."""
        review = [
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="hola",
                english="hello",
                topic="greetings",
                difficulty=1,
            ),
        ]
        new = [
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="adios",
                english="goodbye",
                topic="greetings",
                difficulty=1,
            ),
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="chela",
                english="beer",
                topic="food",
                difficulty=1,
            ),
        ]
        scheduler = CurriculumScheduler(MagicMock())
        topic = scheduler._pick_topic(review, new)
        assert topic == "greetings"  # 2 greetings vs 1 food


class TestCreateVoiceFocus:
    """Tests for _create_voice_focus method."""

    def test_voice_focus_with_review_items(self):
        """Should include review words."""
        review = [
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="hola",
                english="hello",
                topic="greetings",
                difficulty=1,
            ),
        ]
        scheduler = CurriculumScheduler(MagicMock())
        focus = scheduler._create_voice_focus(review, [])
        assert "Review: hola" in focus

    def test_voice_focus_with_new_items(self):
        """Should include new words."""
        new = [
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="adios",
                english="goodbye",
                topic="greetings",
                difficulty=1,
            ),
        ]
        scheduler = CurriculumScheduler(MagicMock())
        focus = scheduler._create_voice_focus([], new)
        assert "New: adios" in focus

    def test_voice_focus_with_both(self):
        """Should include both review and new words separated by pipe."""
        review = [
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="hola",
                english="hello",
                topic="greetings",
                difficulty=1,
            ),
        ]
        new = [
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish="adios",
                english="goodbye",
                topic="greetings",
                difficulty=1,
            ),
        ]
        scheduler = CurriculumScheduler(MagicMock())
        focus = scheduler._create_voice_focus(review, new)
        assert "Review: hola" in focus
        assert "New: adios" in focus
        assert " | " in focus

    def test_voice_focus_empty_returns_default(self):
        """Should return default when no items."""
        scheduler = CurriculumScheduler(MagicMock())
        focus = scheduler._create_voice_focus([], [])
        assert focus == "Free conversation practice"

    def test_voice_focus_limits_review_to_five(self):
        """Should only include first 5 review items."""
        review = [
            CurriculumItem(
                content_type=ContentType.PHRASE,
                spanish=f"word{i}",
                english=f"word{i}",
                topic="test",
                difficulty=1,
            )
            for i in range(10)
        ]
        scheduler = CurriculumScheduler(MagicMock())
        focus = scheduler._create_voice_focus(review, [])
        # Should have exactly 5 words
        assert "word0" in focus
        assert "word4" in focus
        assert "word5" not in focus


class TestGenerateExercises:
    """Tests for _generate_exercises method."""

    def test_generate_translate_exercises(self):
        """Should generate translation exercises for review items.

        Note: The prompt type selection determines whether exercises are
        translate_to_english (recognition) or translate_to_spanish (production).
        With default skills and mastery level 3, items get recognition prompts.
        """
        review = [
            CurriculumItem(
                id=1,
                content_type=ContentType.PHRASE,
                spanish="hola",
                english="hello",
                mexican_notes="Common greeting",
                topic="greetings",
                difficulty=1,
            ),
        ]
        scheduler = CurriculumScheduler(MagicMock())
        exercises = scheduler._generate_exercises(review, [])

        # With default skills, should generate recognition exercises (Spanish -> English)
        translate_exercises = [
            e for e in exercises
            if e["type"] in ("translate_to_spanish", "translate_to_english")
        ]
        assert len(translate_exercises) == 1
        assert translate_exercises[0]["item_id"] == 1

    def test_generate_new_vocab_exercises(self):
        """Should generate vocab introduction for new items."""
        new = [
            CurriculumItem(
                id=2,
                content_type=ContentType.PHRASE,
                spanish="adios",
                english="goodbye",
                example_sentence="Adios, nos vemos!",
                mexican_notes="Casual farewell",
                topic="greetings",
                difficulty=1,
            ),
        ]
        scheduler = CurriculumScheduler(MagicMock())
        exercises = scheduler._generate_exercises([], new)

        vocab_exercises = [e for e in exercises if e["type"] == "new_vocab"]
        assert len(vocab_exercises) == 1
        assert "adios" in vocab_exercises[0]["prompt"]
        assert vocab_exercises[0]["item_id"] == 2

    def test_generate_fill_blank_exercises(self):
        """Should generate fill-blank for items 3-5 with example sentences."""
        review = [
            CurriculumItem(
                id=i,
                content_type=ContentType.PHRASE,
                spanish=f"word{i}",
                english=f"meaning{i}",
                example_sentence=f"This is word{i} in a sentence.",
                topic="test",
                difficulty=1,
            )
            for i in range(6)
        ]
        scheduler = CurriculumScheduler(MagicMock())
        exercises = scheduler._generate_exercises(review, [])

        fill_exercises = [e for e in exercises if e["type"] == "fill_blank"]
        # Items at indices 3 and 4 should have fill-blank
        assert len(fill_exercises) == 2

    def test_generate_exercises_limits_translate_to_three(self):
        """Should only generate 3 translation exercises."""
        review = [
            CurriculumItem(
                id=i,
                content_type=ContentType.PHRASE,
                spanish=f"word{i}",
                english=f"meaning{i}",
                topic="test",
                difficulty=1,
            )
            for i in range(10)
        ]
        scheduler = CurriculumScheduler(MagicMock())
        exercises = scheduler._generate_exercises(review, [])

        # Translation exercises can be either direction based on prompt type
        translate_exercises = [
            e for e in exercises
            if e["type"] in ("translate_to_spanish", "translate_to_english")
        ]
        assert len(translate_exercises) == 3

    def test_generate_exercises_limits_new_vocab_to_two(self):
        """Should only generate 2 new vocab exercises."""
        new = [
            CurriculumItem(
                id=i,
                content_type=ContentType.PHRASE,
                spanish=f"new{i}",
                english=f"newmeaning{i}",
                example_sentence=f"Example {i}",
                topic="test",
                difficulty=1,
            )
            for i in range(5)
        ]
        scheduler = CurriculumScheduler(MagicMock())
        exercises = scheduler._generate_exercises([], new)

        vocab_exercises = [e for e in exercises if e["type"] == "new_vocab"]
        assert len(vocab_exercises) == 2

    def test_generate_exercises_empty_returns_empty_list(self):
        """Should return empty list when no items."""
        scheduler = CurriculumScheduler(MagicMock())
        exercises = scheduler._generate_exercises([], [])
        assert exercises == []

    def test_fill_blank_skips_items_without_example(self):
        """Should skip fill-blank for items without example sentences."""
        review = [
            CurriculumItem(
                id=i,
                content_type=ContentType.PHRASE,
                spanish=f"word{i}",
                english=f"meaning{i}",
                example_sentence=None,  # No example
                topic="test",
                difficulty=1,
            )
            for i in range(6)
        ]
        scheduler = CurriculumScheduler(MagicMock())
        exercises = scheduler._generate_exercises(review, [])

        fill_exercises = [e for e in exercises if e["type"] == "fill_blank"]
        assert len(fill_exercises) == 0
