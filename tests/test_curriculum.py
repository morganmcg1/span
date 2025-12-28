"""Tests for curriculum content and scheduling."""

import pytest

from span.curriculum.content import SEED_CONTENT
from span.db.models import ContentType


class TestSeedContent:
    """Tests for the seed curriculum content."""

    def test_seed_content_not_empty(self):
        """Should have seed content."""
        assert len(SEED_CONTENT) > 0

    def test_all_items_have_required_fields(self):
        """All items should have spanish, english, and topic."""
        for item in SEED_CONTENT:
            assert item.spanish, f"Missing spanish for item"
            assert item.english, f"Missing english for {item.spanish}"
            assert item.topic, f"Missing topic for {item.spanish}"

    def test_all_items_have_valid_content_type(self):
        """All items should have a valid content type."""
        for item in SEED_CONTENT:
            assert isinstance(item.content_type, ContentType)

    def test_difficulty_in_valid_range(self):
        """Difficulty should be 1-5."""
        for item in SEED_CONTENT:
            assert 1 <= item.difficulty <= 5, f"Invalid difficulty for {item.spanish}"

    def test_has_multiple_topics(self):
        """Should cover multiple topics."""
        topics = set(item.topic for item in SEED_CONTENT)
        assert len(topics) >= 3

    def test_has_texting_content(self):
        """Should include texting abbreviations."""
        texting_items = [
            item for item in SEED_CONTENT
            if item.content_type == ContentType.TEXTING
        ]
        assert len(texting_items) >= 3

    def test_has_mexican_notes(self):
        """Most items should have Mexican context notes."""
        items_with_notes = [
            item for item in SEED_CONTENT
            if item.mexican_notes
        ]
        # At least half should have notes
        assert len(items_with_notes) >= len(SEED_CONTENT) // 2
