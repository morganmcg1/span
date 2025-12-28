"""Curriculum scheduling and daily plan generation.

Implements:
- i+1 (Krashen): Select content just beyond current ability
- Interleaving (Bjork): Mix topics for better transfer
- ZPD-based selection: Zone of proximal development
"""

from dataclasses import dataclass

from span.db.database import Database
from span.db.models import CurriculumItem

from span.curriculum.selector import (
    SelectionContext,
    select_next_items,
    select_prompt_type,
    get_interleaved_topic_sequence,
)


@dataclass
class DailyPlan:
    """Plan for today's learning activities."""

    review_items: list[CurriculumItem]
    new_items: list[CurriculumItem]
    suggested_topic: str
    voice_lesson_focus: str
    telegram_exercises: list[dict]
    interleaved_topics: list[str]  # Topics for interleaved practice


class CurriculumScheduler:
    """Generates daily learning plans based on spaced repetition and i+1."""

    def __init__(self, db: Database):
        self.db = db

    def get_items_due_for_review(self, user_id: int, limit: int = 10) -> list[CurriculumItem]:
        """Get items that are due for review."""
        return self.db.get_items_due_for_review(user_id, limit)

    def get_new_items(self, user_id: int, count: int = 3) -> list[CurriculumItem]:
        """Get new items the user hasn't learned yet (legacy method)."""
        return self.db.get_new_items_for_user(user_id, count)

    def create_daily_plan(self, user_id: int) -> DailyPlan:
        """Generate today's learning plan using adaptive selection.

        Uses i+1 principle to select items at the learner's ZPD.
        Applies interleaving to mix topics for better transfer.
        """
        # Get learner's skills and profile for adaptive selection
        skills = self.db.get_or_create_skill_dimensions(user_id)
        profile = self.db.get_or_create_learner_profile(user_id)

        # Get recent topics to avoid blocking
        recent_sessions = self.db.get_recent_sessions(user_id, limit=3)
        recent_topics = [s.topic for s in recent_sessions if s.topic]

        # Create selection context
        context = SelectionContext(
            user_id=user_id,
            skills=skills,
            profile=profile,
            recent_topics=recent_topics,
        )

        # Use adaptive selector for item selection
        review_items, new_items = select_next_items(
            self.db,
            context,
            review_limit=10,
            new_limit=3,
        )

        # Get interleaved topic sequence (Bjork)
        interleaved_topics = get_interleaved_topic_sequence(self.db, user_id, num_topics=3)

        # Pick a topic based on items (prefer topics from interleaved sequence)
        suggested_topic = self._pick_topic(review_items, new_items, interleaved_topics)

        # Create focus for voice lesson
        voice_focus = self._create_voice_focus(review_items, new_items)

        # Generate Telegram exercises with prompt type selection
        exercises = self._generate_exercises(review_items, new_items, skills)

        return DailyPlan(
            review_items=review_items,
            new_items=new_items,
            suggested_topic=suggested_topic,
            voice_lesson_focus=voice_focus,
            telegram_exercises=exercises,
            interleaved_topics=interleaved_topics,
        )

    def _pick_topic(
        self,
        review_items: list[CurriculumItem],
        new_items: list[CurriculumItem],
        interleaved_topics: list[str] | None = None,
    ) -> str:
        """Pick a topic to focus on today.

        Prefers topics from the interleaved sequence if available.
        """
        all_items = review_items + new_items
        if not all_items:
            return "general conversation"

        # Count topics from current items
        topic_counts: dict[str, int] = {}
        for item in all_items:
            topic_counts[item.topic] = topic_counts.get(item.topic, 0) + 1

        # Prefer topics from interleaved sequence (Bjork's interleaving)
        if interleaved_topics:
            for topic in interleaved_topics:
                if topic in topic_counts:
                    return topic

        # Fall back to most common topic
        return max(topic_counts, key=topic_counts.get)

    def _create_voice_focus(
        self, review_items: list[CurriculumItem], new_items: list[CurriculumItem]
    ) -> str:
        """Create a focus description for the voice lesson."""
        parts = []

        if review_items:
            review_words = [item.spanish for item in review_items[:5]]
            parts.append(f"Review: {', '.join(review_words)}")

        if new_items:
            new_words = [item.spanish for item in new_items]
            parts.append(f"New: {', '.join(new_words)}")

        if not parts:
            return "Free conversation practice"

        return " | ".join(parts)

    def _generate_exercises(
        self,
        review_items: list[CurriculumItem],
        new_items: list[CurriculumItem],
        skills: "SkillDimensions | None" = None,
    ) -> list[dict]:
        """Generate exercises for Telegram with prompt type selection.

        Uses Matuschak's prompt progression based on mastery level.
        """
        from span.db.models import SkillDimensions

        exercises = []
        skills = skills or SkillDimensions()

        # Translation exercises for review items (production prompts)
        for item in review_items[:3]:
            # Determine prompt type based on item's skill contributions
            prompt_type = select_prompt_type(skills, item, item_mastery_level=3)

            if prompt_type in ("recognition", "cued_production"):
                # Recognition: Spanish to English
                exercises.append({
                    "type": "translate_to_english",
                    "prompt": f"What does '{item.spanish}' mean?",
                    "answer": item.english,
                    "hint": item.mexican_notes,
                    "item_id": item.id,
                    "prompt_type": prompt_type,
                })
            else:
                # Production: English to Spanish
                exercises.append({
                    "type": "translate_to_spanish",
                    "prompt": f"How do you say '{item.english}' in Mexican Spanish?",
                    "answer": item.spanish,
                    "hint": item.mexican_notes,
                    "item_id": item.id,
                    "prompt_type": prompt_type,
                })

        # New vocabulary introduction (recognition prompts)
        for item in new_items[:2]:
            exercises.append({
                "type": "new_vocab",
                "prompt": f"**New word**: {item.spanish}\n\n_{item.english}_\n\nExample: {item.example_sentence}",
                "note": item.mexican_notes,
                "item_id": item.id,
                "prompt_type": "recognition",
                "skill_contributions": item.skill_contributions,
            })

        # Fill in the blank for harder items (application prompts)
        for item in review_items[3:5]:
            if item.example_sentence:
                blanked = item.example_sentence.replace(item.spanish, "______")
                if blanked != item.example_sentence:
                    exercises.append({
                        "type": "fill_blank",
                        "prompt": f"Fill in the blank:\n\n{blanked}\n\n(Hint: {item.english})",
                        "answer": item.spanish,
                        "item_id": item.id,
                        "prompt_type": "application",
                    })

        return exercises
