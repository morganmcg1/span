"""Recall item generation for spaced repetition and reinforcement.

Pulls items from multiple sources:
1. Weak areas from learner profile (pronunciation/vocab issues)
2. Items due for review from user_progress (SM-2)
3. Strong areas for confidence reinforcement
4. Random curriculum items for variety
"""

import random
from dataclasses import dataclass

from span.db.database import Database


@dataclass
class RecallItem:
    """A single item for recall practice."""
    spanish: str
    english: str
    category: str  # weak_area, due_review, strong_area, curriculum
    hint: str | None = None
    pronunciation_note: str | None = None
    example: str | None = None


def get_recall_items(db: Database, user_id: int, max_items: int = 6) -> dict:
    """Generate personalized recall items for a user.

    Returns a dict with:
    - items: list of recall items to practice
    - focus_message: brief guidance for Lupita
    """
    items: list[dict] = []

    # Get learner profile for weak/strong topics
    profile = db.get_or_create_learner_profile(user_id)

    # 1. Weak areas from profile (priority - these need the most work)
    weak_items = _items_from_weak_topics(profile.weak_topics, max_count=2)
    items.extend(weak_items)

    # 2. Items due for SM-2 review
    due_items = db.get_items_due_for_review(user_id, limit=3)
    for item in due_items[:2]:
        items.append({
            "spanish": item.spanish,
            "english": item.english,
            "category": "due_review",
            "hint": item.mexican_notes,
            "example": item.example_sentence,
        })

    # 3. Strong areas for confidence (quick wins)
    strong_items = _items_from_strong_topics(profile.strong_topics, max_count=1)
    items.extend(strong_items)

    # 4. Random curriculum items if we need more
    if len(items) < max_items:
        all_curriculum = db.get_all_curriculum_items()
        # Filter out items already in our list
        existing_spanish = {i["spanish"] for i in items}
        available = [c for c in all_curriculum if c.spanish not in existing_spanish]

        if available:
            random.shuffle(available)
            for item in available[:max_items - len(items)]:
                items.append({
                    "spanish": item.spanish,
                    "english": item.english,
                    "category": "curriculum",
                    "hint": item.mexican_notes,
                    "example": item.example_sentence,
                })

    # Shuffle to mix categories
    random.shuffle(items)

    # Build focus message based on what we have
    focus_parts = []
    categories = {i["category"] for i in items}
    if "weak_area" in categories:
        focus_parts.append("pronunciation challenges")
    if "due_review" in categories:
        focus_parts.append("vocabulary due for review")
    if "strong_area" in categories:
        focus_parts.append("confident areas to reinforce")

    focus_message = f"Today's focus: {', '.join(focus_parts) or 'general vocabulary practice'}."

    return {
        "items": items,
        "focus_message": focus_message,
        "total_count": len(items),
    }


def _items_from_weak_topics(weak_topics: list[str], max_count: int = 2) -> list[dict]:
    """Extract recall items from weak topic descriptions.

    Weak topics are typically descriptions like:
    - "pronunciation of 'cacahuate'"
    - "confusing 'suena' and 'sueña'"
    - "pronunciation of 'prefiero' requires multiple attempts"
    """
    items = []

    # Common patterns in weak topics
    pronunciation_patterns = [
        ("cacahuate", "peanut", "Focus on the 'hua' sound - wah"),
        ("prefiero", "I prefer", "Roll the 'r' slightly, stress on 'fie'"),
        ("canela", "cinnamon", "Stress on second syllable: ca-NE-la"),
        ("mermelada", "jam/marmalade", "Four syllables: mer-me-LA-da"),
        ("azúcar", "sugar", "Stress on 'zú': a-ZÚ-car"),
    ]

    for topic in weak_topics[:max_count * 2]:  # Check more to find matches
        if len(items) >= max_count:
            break

        topic_lower = topic.lower()

        # Check for known pronunciation issues
        for spanish, english, note in pronunciation_patterns:
            if spanish in topic_lower and len(items) < max_count:
                items.append({
                    "spanish": spanish,
                    "english": english,
                    "category": "weak_area",
                    "pronunciation_note": note,
                    "hint": f"You've been working on this - {topic}",
                })
                break

        # Check for vocabulary confusion patterns
        if "confusing" in topic_lower or "mixing" in topic_lower:
            # Try to extract the confused words
            if "suena" in topic_lower and "sueña" in topic_lower:
                items.append({
                    "spanish": "sueña vs suena",
                    "english": "dreams (verb) vs sounds",
                    "category": "weak_area",
                    "pronunciation_note": "sueña has ñ (nye sound) for 'dreams', suena is 'sounds'",
                    "hint": "These are easy to confuse - the ñ makes all the difference!",
                })

    return items


def _items_from_strong_topics(strong_topics: list[str], max_count: int = 1) -> list[dict]:
    """Extract recall items from strong topic descriptions.

    Strong topics are typically descriptions like:
    - "uses 'ahorita' naturally"
    - "can produce preference statements with 'prefiero'"
    """
    items = []

    # Common patterns in strong topics
    strong_patterns = [
        ("ahorita", "right now / in a bit", "Mexican way of saying 'now' - can mean immediately or soon!"),
        ("prefiero", "I prefer", "Great for expressing preferences"),
    ]

    for topic in strong_topics[:max_count * 2]:
        if len(items) >= max_count:
            break

        topic_lower = topic.lower()

        for spanish, english, note in strong_patterns:
            if spanish in topic_lower and len(items) < max_count:
                items.append({
                    "spanish": spanish,
                    "english": english,
                    "category": "strong_area",
                    "hint": note,
                    "example": f"Quick review - you're good at this!",
                })
                break

    return items
