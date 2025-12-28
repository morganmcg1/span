"""Database models for Span."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum


class LessonType(Enum):
    VOICE_CONVERSATION = "voice_conversation"
    TEXT_VOCABULARY = "text_vocabulary"
    TEXT_PRACTICE = "text_practice"


class ContentType(Enum):
    VOCABULARY = "vocabulary"
    PHRASE = "phrase"
    GRAMMAR = "grammar"
    TEXTING = "texting"


class SkillLevel(IntEnum):
    """Categorical skill levels for LLM-friendly assessment.

    Using integers 1-5 instead of floats because LLMs are better at
    choosing discrete categories with clear descriptions.
    """

    NONE = 1  # No exposure - cannot recognize or produce
    EXPOSURE = 2  # Has seen/heard - may recognize with hints
    RECOGNITION = 3  # Can understand when heard/read - cannot produce reliably
    PRODUCTION = 4  # Can produce with effort - may need time or make errors
    FLUENT = 5  # Automatic - produces quickly and accurately


@dataclass
class SkillDimensions:
    """Multi-dimensional skill model tracking learner competencies.

    Each dimension is scored 1-5 using SkillLevel categories.
    This enables i+1 (Krashen) adaptive content selection.
    """

    id: int | None = None
    user_id: int = 0

    # Core competencies
    vocabulary_recognition: int = 1  # Hear/read → understand
    vocabulary_production: int = 1  # Idea → produce Spanish
    pronunciation: int = 1  # Phoneme accuracy
    grammar_receptive: int = 1  # Understand structures
    grammar_productive: int = 1  # Use structures correctly
    conversational_flow: int = 1  # Fillers, repairs, turn-taking
    cultural_pragmatics: int = 1  # When to use what (register)

    # Priority skills: Storytelling & Hypotheticals
    narration: int = 1  # Tell stories, sequence events in past tense
    conditionals: int = 1  # Express hypotheticals ("si yo fuera...", "me gustaría...")

    updated_at: datetime | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, int]:
        """Return skill dimensions as a dictionary for comparison."""
        return {
            "vocabulary_recognition": self.vocabulary_recognition,
            "vocabulary_production": self.vocabulary_production,
            "pronunciation": self.pronunciation,
            "grammar_receptive": self.grammar_receptive,
            "grammar_productive": self.grammar_productive,
            "conversational_flow": self.conversational_flow,
            "cultural_pragmatics": self.cultural_pragmatics,
            "narration": self.narration,
            "conditionals": self.conditionals,
        }


@dataclass
class User:
    """A user of the app."""

    id: int | None = None
    phone_number: str = ""
    telegram_id: int = 0
    timezone: str = "Europe/Dublin"
    preferred_call_times: str = '["09:50"]'
    created_at: datetime | None = None


@dataclass
class CurriculumItem:
    """A single learnable item (word, phrase, grammar point).

    The skill_requirements and skill_contributions enable i+1 adaptive selection:
    - skill_requirements: Min skill levels (1-5) needed to attempt this item
    - skill_contributions: Target skill levels this item develops when mastered
    """

    id: int | None = None
    content_type: ContentType = ContentType.VOCABULARY
    spanish: str = ""
    english: str = ""
    example_sentence: str | None = None
    mexican_notes: str | None = None
    topic: str = ""
    difficulty: int = 1  # Legacy field, kept for backward compatibility

    # Adaptive selection fields (new)
    prerequisite_items: list[int] = field(default_factory=list)  # Item IDs learner should know first
    skill_requirements: dict[str, int] = field(default_factory=dict)  # Min skill levels to attempt (1-5)
    skill_contributions: dict[str, int] = field(default_factory=dict)  # Target skill level this develops
    cefr_level: str = "A1"  # A1, A2, B1, B2, C1, C2
    prompt_types: list[str] = field(default_factory=list)  # recognition, production, application

    created_at: datetime | None = None


@dataclass
class UserProgress:
    """SM-2 spaced repetition state for each item."""

    id: int | None = None
    user_id: int = 0
    item_id: int = 0
    easiness_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    next_review: datetime | None = None
    last_reviewed: datetime | None = None


@dataclass
class LessonSession:
    """Record of a completed lesson."""

    id: int | None = None
    user_id: int = 0
    lesson_type: LessonType = LessonType.VOICE_CONVERSATION
    topic: str = ""
    items_covered: str = "[]"
    performance_score: float | None = None
    duration_seconds: int | None = None
    transcript: str | None = None
    notes: str | None = None
    created_at: datetime | None = None


@dataclass
class ConversationMessage:
    """Message history for continuity."""

    id: int | None = None
    user_id: int = 0
    session_id: int | None = None
    role: str = "user"
    content: str = ""
    channel: str = "telegram"
    audio_path: str | None = None  # Path to audio file for voice messages
    created_at: datetime | None = None


@dataclass
class LearnerProfile:
    """Persistent learner profile - core memory block."""

    id: int | None = None
    user_id: int = 0
    name: str | None = None
    native_language: str = "English"
    location: str | None = None
    level: str = "beginner"  # beginner, intermediate, advanced
    strong_topics: list[str] = field(default_factory=list)
    weak_topics: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    conversation_style: str = "casual"  # casual, structured, immersive
    notes: str | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None

    def to_context_block(self) -> str:
        """Convert profile to a context string for LLM."""
        parts = []
        if self.name:
            parts.append(f"Name: {self.name}")
        if self.location:
            parts.append(f"From: {self.location}")
        parts.append(f"Level: {self.level}")
        parts.append(f"Native language: {self.native_language}")
        if self.strong_topics:
            parts.append(f"Strong at: {', '.join(self.strong_topics)}")
        if self.weak_topics:
            parts.append(f"Needs work on: {', '.join(self.weak_topics)}")
        if self.interests:
            parts.append(f"Interests: {', '.join(self.interests)}")
        if self.goals:
            parts.append(f"Goals: {', '.join(self.goals)}")
        parts.append(f"Prefers: {self.conversation_style} conversation style")
        if self.notes:
            parts.append(f"Notes: {self.notes}")
        return "\n".join(parts)


@dataclass
class ExtractedFact:
    """A fact extracted from conversation for long-term memory."""

    id: int | None = None
    user_id: int = 0
    fact_type: str = ""  # name, location, interest, goal, strength, weakness, milestone
    fact_value: str = ""
    source_channel: str | None = None
    confidence: float = 1.0
    created_at: datetime | None = None
