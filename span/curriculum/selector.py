"""Adaptive content selector implementing i+1 (zone of proximal development).

This module selects curriculum items based on the learner's current skill
dimensions, implementing Krashen's i+1 principle and Bjork's interleaving.

Key concepts:
- ZPD (Zone of Proximal Development): Content just beyond current ability
- Readiness: How prepared the learner is for a given item
- Interleaving: Mixing topics to improve transfer (Bjork)
"""

from dataclasses import dataclass
from datetime import datetime

from span.db.database import Database
from span.db.models import CurriculumItem, LearnerProfile, SkillDimensions


@dataclass
class SelectionContext:
    """Context for content selection decisions."""

    user_id: int
    skills: SkillDimensions
    profile: LearnerProfile
    recent_topics: list[str]  # Topics from recent sessions to avoid blocking


class Readiness:
    """Readiness levels for content selection."""

    NOT_READY = "not_ready"  # Too far ahead (i+3 or more)
    STRETCH = "stretch"  # Challenging but possible (i+2)
    READY = "ready"  # Perfect ZPD (i+1)
    MASTERED = "mastered"  # Already knows this


def compute_readiness(skills: SkillDimensions, requirements: dict[str, int]) -> str:
    """Compute learner's readiness for an item based on skill requirements.

    Returns categorical readiness: 'not_ready', 'stretch', 'ready', 'mastered'

    This implements the i+1 principle by checking how the learner's current
    skills compare to what the item requires.
    """
    if not requirements:
        return Readiness.READY  # No requirements = entry-level item

    skill_dict = skills.to_dict()
    gaps = []

    for skill_name, required_level in requirements.items():
        current_level = skill_dict.get(skill_name, 1)
        gap = required_level - current_level
        gaps.append(gap)

    if not gaps:
        return Readiness.READY

    max_gap = max(gaps)
    avg_gap = sum(gaps) / len(gaps)

    # Categorize based on gap analysis
    if max_gap > 2:
        return Readiness.NOT_READY  # Too far ahead (i+3 or more)
    elif max_gap == 2 or avg_gap > 1:
        return Readiness.STRETCH  # Challenging but possible (i+2)
    elif max_gap <= 0 and avg_gap <= 0:
        return Readiness.MASTERED  # Already knows this
    else:
        return Readiness.READY  # Perfect ZPD (i+1)


def select_next_items(
    db: Database,
    context: SelectionContext,
    review_limit: int = 5,
    new_limit: int = 3,
) -> tuple[list[CurriculumItem], list[CurriculumItem]]:
    """Select items for the next learning session.

    Implements i+1 by selecting items at the learner's zone of proximal development.

    Returns:
        Tuple of (review_items, new_items)
    """
    # 1. Get items due for review (SM-2)
    review_items = db.get_items_due_for_review(context.user_id, limit=review_limit)

    # 2. Get items the user hasn't learned yet
    candidates = db.get_new_items_for_user(context.user_id, limit=50)

    # 3. Filter to ZPD: items marked 'ready' or 'stretch'
    zpd_items = []
    for item in candidates:
        readiness = compute_readiness(context.skills, item.skill_requirements)
        if readiness in (Readiness.READY, Readiness.STRETCH):
            zpd_items.append((item, readiness))

    # 4. Sort: prefer 'ready' items over 'stretch' items
    zpd_items.sort(key=lambda x: x[1] == Readiness.STRETCH)

    # 5. Apply interleaving (Bjork): mix topics, don't block
    if review_items:
        review_topics = {item.topic for item in review_items}
        # Prefer new items from different topics
        zpd_items.sort(
            key=lambda x: (
                x[0].topic in review_topics,  # False (not in review) sorts first
                x[1] == Readiness.STRETCH,  # Ready before stretch
            )
        )

    # 6. Prioritize weak areas (but not exclusively - desirable difficulty)
    weak_topics = set(context.profile.weak_topics)
    strong_topics = set(context.profile.strong_topics)

    weak_items = []
    varied_items = []
    strong_items = []

    for item, readiness in zpd_items:
        if item.topic in weak_topics:
            weak_items.append(item)
        elif item.topic in strong_topics:
            strong_items.append(item)
        else:
            varied_items.append(item)

    # Mix: 60% weak areas, 30% varied, 10% strong (for reinforcement)
    new_items = []
    weak_count = max(1, int(new_limit * 0.6))
    varied_count = max(1, int(new_limit * 0.3))

    new_items.extend(weak_items[:weak_count])
    new_items.extend(varied_items[:varied_count])
    new_items.extend(strong_items[:max(0, new_limit - len(new_items))])

    # Ensure we don't exceed the limit
    new_items = new_items[:new_limit]

    return review_items, new_items


def select_prompt_type(
    skills: SkillDimensions,
    item: CurriculumItem,
    item_mastery_level: int = 1,
) -> str:
    """Select the appropriate prompt type based on mastery stage.

    Implements Matuschak's prompt progression:
    - New items: recognition
    - Learning: cued production
    - Consolidating: free production
    - Mastered: application
    - Maintained: salience (interleaved review)

    Args:
        skills: Current skill dimensions
        item: The curriculum item
        item_mastery_level: The learner's mastery level for this specific item (1-5)

    Returns:
        Prompt type: 'recognition', 'cued_production', 'free_production', 'application'
    """
    # Use item's available prompt types
    available_types = item.prompt_types or ["recognition", "production"]

    if item_mastery_level <= 2:
        # New/Exposure: Focus on recognition
        return "recognition" if "recognition" in available_types else available_types[0]
    elif item_mastery_level == 3:
        # Recognition: Move to cued production
        return "cued_production" if "production" in available_types else "recognition"
    elif item_mastery_level == 4:
        # Production: Free production
        return "free_production" if "production" in available_types else "recognition"
    else:
        # Fluent: Application in novel contexts
        return "application" if "application" in available_types else "free_production"


def get_interleaved_topic_sequence(
    db: Database,
    user_id: int,
    num_topics: int = 3,
) -> list[str]:
    """Get a sequence of topics for interleaved practice.

    Implements Bjork's interleaving principle by mixing topics rather than
    blocking them together.

    Args:
        db: Database instance
        user_id: User ID
        num_topics: Number of topics to include

    Returns:
        List of topic names in interleaved order
    """
    # Get all curriculum items to find unique topics
    all_items = db.get_all_curriculum_items()
    topics = list({item.topic for item in all_items})

    # Get user's profile for weak/strong topics
    profile = db.get_or_create_learner_profile(user_id)
    weak_topics = set(profile.weak_topics)
    strong_topics = set(profile.strong_topics)
    neutral_topics = [t for t in topics if t not in weak_topics and t not in strong_topics]

    # Build interleaved sequence: weak, neutral, weak, strong, neutral, etc.
    sequence = []
    weak_list = list(weak_topics)
    strong_list = list(strong_topics)

    i = 0
    while len(sequence) < num_topics:
        # Pattern: weak, neutral, weak, strong, neutral, ...
        if i % 5 in (0, 2):  # Weak slots
            if weak_list:
                sequence.append(weak_list.pop(0))
            elif neutral_topics:
                sequence.append(neutral_topics.pop(0))
        elif i % 5 == 3:  # Strong slot
            if strong_list:
                sequence.append(strong_list.pop(0))
            elif neutral_topics:
                sequence.append(neutral_topics.pop(0))
        else:  # Neutral slots
            if neutral_topics:
                sequence.append(neutral_topics.pop(0))
            elif weak_list:
                sequence.append(weak_list.pop(0))
            elif strong_list:
                sequence.append(strong_list.pop(0))

        i += 1

        # Safety: avoid infinite loop if we run out of topics
        if i > len(topics) * 2:
            break

    return sequence[:num_topics]


def should_advance_skill(
    consecutive_correct: int,
    response_time_ms: int | None,
    current_level: int,
) -> bool:
    """Determine if a skill level should advance based on performance.

    Mastery criteria:
    - NONE (1) → EXPOSURE (2): First successful encounter
    - EXPOSURE (2) → RECOGNITION (3): Understand 2 times in context
    - RECOGNITION (3) → PRODUCTION (4): Produce correctly 2 times
    - PRODUCTION (4) → FLUENT (5): Produce correctly 3 times, each under 3 seconds

    Args:
        consecutive_correct: Number of consecutive correct responses
        response_time_ms: Response time in milliseconds (None if not measured)
        current_level: Current skill level (1-5)

    Returns:
        True if the skill should advance
    """
    if current_level >= 5:
        return False  # Already at max

    if current_level == 1:
        # NONE → EXPOSURE: Any correct response
        return consecutive_correct >= 1
    elif current_level == 2:
        # EXPOSURE → RECOGNITION: 2 correct in context
        return consecutive_correct >= 2
    elif current_level == 3:
        # RECOGNITION → PRODUCTION: 2 correct productions
        return consecutive_correct >= 2
    elif current_level == 4:
        # PRODUCTION → FLUENT: 3 correct, each under 3 seconds
        if response_time_ms is None:
            return consecutive_correct >= 3
        return consecutive_correct >= 3 and response_time_ms < 3000

    return False
