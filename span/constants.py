"""Shared constants for the Span application."""

# Skill dimension names - the canonical list
SKILL_NAMES = (
    "vocabulary_recognition",
    "vocabulary_production",
    "pronunciation",
    "grammar_receptive",
    "grammar_productive",
    "conversational_flow",
    "cultural_pragmatics",
    "narration",
    "conditionals",
)

# As a frozenset for O(1) membership testing
VALID_SKILLS = frozenset(SKILL_NAMES)
