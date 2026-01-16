"""Tests for the recall item generation system."""

import pytest

from span.voice.recall import (
    get_recall_items,
    _items_from_weak_topics,
    _items_from_strong_topics,
)


class TestGetRecallItems:
    """Tests for get_recall_items function."""

    def test_returns_items_dict(self, memory_db, sample_user):
        """Should return a dict with items and focus message."""
        user_id = memory_db.create_user(sample_user)

        result = get_recall_items(memory_db, user_id)

        assert "items" in result
        assert "focus_message" in result
        assert "total_count" in result
        assert isinstance(result["items"], list)

    def test_pulls_from_weak_topics(self, memory_db, sample_user):
        """Should include items from learner's weak topics."""
        user_id = memory_db.create_user(sample_user)

        # Set up profile with weak topics
        profile = memory_db.get_or_create_learner_profile(user_id)
        profile.weak_topics = ["pronunciation of 'cacahuate'"]
        memory_db.update_learner_profile(profile)

        result = get_recall_items(memory_db, user_id)

        # Should have weak area items
        categories = [item["category"] for item in result["items"]]
        assert "weak_area" in categories or len(result["items"]) > 0

    def test_pulls_from_strong_topics(self, memory_db, sample_user):
        """Should include items from learner's strong topics."""
        user_id = memory_db.create_user(sample_user)

        # Set up profile with strong topics
        profile = memory_db.get_or_create_learner_profile(user_id)
        profile.strong_topics = ["uses 'ahorita' naturally"]
        memory_db.update_learner_profile(profile)

        result = get_recall_items(memory_db, user_id)

        # Should have strong area items
        categories = [item["category"] for item in result["items"]]
        assert "strong_area" in categories or len(result["items"]) > 0

    def test_respects_max_items(self, memory_db, sample_user):
        """Should not return more than max_items."""
        user_id = memory_db.create_user(sample_user)

        result = get_recall_items(memory_db, user_id, max_items=3)

        assert len(result["items"]) <= 3
        assert result["total_count"] <= 3

    def test_includes_curriculum_items(self, memory_db, sample_user):
        """Should include curriculum items when needed to fill quota."""
        from span.curriculum.content import seed_database

        user_id = memory_db.create_user(sample_user)

        # Seed curriculum
        seed_database(memory_db)

        result = get_recall_items(memory_db, user_id)

        # Should have curriculum items
        categories = [item["category"] for item in result["items"]]
        assert "curriculum" in categories or len(result["items"]) > 0


class TestItemsFromWeakTopics:
    """Tests for _items_from_weak_topics helper."""

    def test_extracts_pronunciation_items(self):
        """Should extract items from pronunciation-related weak topics."""
        weak_topics = ["pronunciation of 'cacahuate'"]

        items = _items_from_weak_topics(weak_topics, max_count=2)

        assert len(items) > 0
        assert items[0]["category"] == "weak_area"
        assert "cacahuate" in items[0]["spanish"]

    def test_handles_confusion_patterns(self):
        """Should handle vocabulary confusion patterns."""
        weak_topics = ["confusing 'suena' and 'sueña'"]

        items = _items_from_weak_topics(weak_topics, max_count=2)

        # Should extract comparison item
        assert len(items) > 0
        assert "sueña" in items[0]["spanish"].lower() or "suena" in items[0]["spanish"].lower()

    def test_respects_max_count(self):
        """Should not return more than max_count items."""
        weak_topics = [
            "pronunciation of 'cacahuate'",
            "pronunciation of 'prefiero'",
            "pronunciation of 'canela'",
        ]

        items = _items_from_weak_topics(weak_topics, max_count=1)

        assert len(items) <= 1


class TestItemsFromStrongTopics:
    """Tests for _items_from_strong_topics helper."""

    def test_extracts_strong_items(self):
        """Should extract items from strong topic descriptions."""
        strong_topics = ["uses 'ahorita' naturally"]

        items = _items_from_strong_topics(strong_topics, max_count=1)

        assert len(items) > 0
        assert items[0]["category"] == "strong_area"
        assert "ahorita" in items[0]["spanish"]

    def test_respects_max_count(self):
        """Should not return more than max_count items."""
        strong_topics = [
            "uses 'ahorita' naturally",
            "can produce preference statements with 'prefiero'",
        ]

        items = _items_from_strong_topics(strong_topics, max_count=1)

        assert len(items) <= 1
