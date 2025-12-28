"""Skill taxonomy and CEFR mapping for adaptive curriculum.

This module defines the skill dimensions, their level descriptions,
and CEFR mappings for use in adaptive content selection and LLM assessment.

Based on research from:
- Andy Matuschak's spaced repetition principles
- Krashen's i+1 comprehensible input hypothesis
- Swain's output hypothesis (pushed output)
- Bjork's desirable difficulties (interleaving, spacing)
"""

from dataclasses import dataclass

from span.constants import SKILL_NAMES
from span.db.models import SkillDimensions, SkillLevel


@dataclass
class SkillLevelDescription:
    """Description of a skill level for LLM assessment."""

    level: SkillLevel
    name: str
    description: str
    example: str


# Generic level descriptions (apply to most skills)
GENERIC_LEVEL_DESCRIPTIONS = {
    SkillLevel.NONE: SkillLevelDescription(
        level=SkillLevel.NONE,
        name="NONE",
        description="No exposure - cannot recognize or produce",
        example="User has not been exposed to this concept",
    ),
    SkillLevel.EXPOSURE: SkillLevelDescription(
        level=SkillLevel.EXPOSURE,
        name="EXPOSURE",
        description="Has seen/heard - may recognize with strong hints",
        example="User heard this once but couldn't recall it",
    ),
    SkillLevel.RECOGNITION: SkillLevelDescription(
        level=SkillLevel.RECOGNITION,
        name="RECOGNITION",
        description="Can understand when heard/read - cannot produce reliably",
        example="User understood when I said it, but couldn't say it themselves",
    ),
    SkillLevel.PRODUCTION: SkillLevelDescription(
        level=SkillLevel.PRODUCTION,
        name="PRODUCTION",
        description="Can produce with effort - needs time or makes minor errors",
        example="User said it correctly but took 5+ seconds to recall",
    ),
    SkillLevel.FLUENT: SkillLevelDescription(
        level=SkillLevel.FLUENT,
        name="FLUENT",
        description="Automatic - produces quickly and accurately",
        example="User used this naturally in conversation without prompting",
    ),
}


# Specialized descriptions for narration skill
NARRATION_LEVEL_DESCRIPTIONS = {
    SkillLevel.NONE: SkillLevelDescription(
        level=SkillLevel.NONE,
        name="NONE",
        description="Cannot sequence events",
        example="Uses only present tense to describe past events",
    ),
    SkillLevel.EXPOSURE: SkillLevelDescription(
        level=SkillLevel.EXPOSURE,
        name="EXPOSURE",
        description="Basic past tense attempts with errors",
        example="'Yo ir al mercado ayer' (significant conjugation errors)",
    ),
    SkillLevel.RECOGNITION: SkillLevelDescription(
        level=SkillLevel.RECOGNITION,
        name="RECOGNITION",
        description="Understands stories told to them",
        example="Follows along with narration but can't retell it",
    ),
    SkillLevel.PRODUCTION: SkillLevelDescription(
        level=SkillLevel.PRODUCTION,
        name="PRODUCTION",
        description="Can narrate with effort",
        example="Uses preterite, some time markers, may mix tenses",
    ),
    SkillLevel.FLUENT: SkillLevelDescription(
        level=SkillLevel.FLUENT,
        name="FLUENT",
        description="Fluent storytelling",
        example="Natural use of preterite/imperfect, time markers, emotional color",
    ),
}


# Specialized descriptions for conditionals skill
CONDITIONALS_LEVEL_DESCRIPTIONS = {
    SkillLevel.NONE: SkillLevelDescription(
        level=SkillLevel.NONE,
        name="NONE",
        description="No hypothetical constructions",
        example="Only states facts, cannot express 'what if' scenarios",
    ),
    SkillLevel.EXPOSURE: SkillLevelDescription(
        level=SkillLevel.EXPOSURE,
        name="EXPOSURE",
        description="Recognizes conditional intent",
        example="Understands 'si...' but can't produce it",
    ),
    SkillLevel.RECOGNITION: SkillLevelDescription(
        level=SkillLevel.RECOGNITION,
        name="RECOGNITION",
        description="Real conditionals only",
        example="'Si tengo tiempo, voy' but not 'si tuviera...'",
    ),
    SkillLevel.PRODUCTION: SkillLevelDescription(
        level=SkillLevel.PRODUCTION,
        name="PRODUCTION",
        description="Hypothetical present with effort",
        example="'Si yo fuera rico, yo... um... compraría un carro'",
    ),
    SkillLevel.FLUENT: SkillLevelDescription(
        level=SkillLevel.FLUENT,
        name="FLUENT",
        description="Natural hypotheticals",
        example="Smoothly uses 'si tuviera/hubiera', 'me gustaría', 'ojalá'",
    ),
}


def get_level_descriptions(skill_name: str) -> dict[SkillLevel, SkillLevelDescription]:
    """Get level descriptions for a specific skill."""
    if skill_name == "narration":
        return NARRATION_LEVEL_DESCRIPTIONS
    elif skill_name == "conditionals":
        return CONDITIONALS_LEVEL_DESCRIPTIONS
    else:
        return GENERIC_LEVEL_DESCRIPTIONS


def format_level_descriptions_for_llm(skill_name: str) -> str:
    """Format level descriptions as text for LLM prompts."""
    descriptions = get_level_descriptions(skill_name)
    lines = []
    for level in SkillLevel:
        desc = descriptions[level]
        lines.append(f"{level.value}-{desc.name}: {desc.description}")
    return "\n".join(lines)


# CEFR level mappings
CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


@dataclass
class CEFRLevelInfo:
    """Information about a CEFR level."""

    level: str
    name: str
    description: str
    typical_skills: dict[str, int]  # Expected skill levels at this CEFR level


CEFR_DEFINITIONS = {
    "A1": CEFRLevelInfo(
        level="A1",
        name="Breakthrough",
        description="Can understand and use familiar everyday expressions and very basic phrases",
        typical_skills={
            "vocabulary_recognition": 3,
            "vocabulary_production": 2,
            "pronunciation": 2,
            "grammar_receptive": 2,
            "grammar_productive": 1,
            "conversational_flow": 1,
            "cultural_pragmatics": 1,
            "narration": 1,
            "conditionals": 1,
        },
    ),
    "A2": CEFRLevelInfo(
        level="A2",
        name="Waystage",
        description="Can communicate in simple and routine tasks on familiar topics",
        typical_skills={
            "vocabulary_recognition": 4,
            "vocabulary_production": 3,
            "pronunciation": 3,
            "grammar_receptive": 3,
            "grammar_productive": 2,
            "conversational_flow": 2,
            "cultural_pragmatics": 2,
            "narration": 2,
            "conditionals": 2,
        },
    ),
    "B1": CEFRLevelInfo(
        level="B1",
        name="Threshold",
        description="Can deal with most situations likely to arise while traveling, produce simple connected text on familiar topics",
        typical_skills={
            "vocabulary_recognition": 5,
            "vocabulary_production": 4,
            "pronunciation": 4,
            "grammar_receptive": 4,
            "grammar_productive": 3,
            "conversational_flow": 3,
            "cultural_pragmatics": 3,
            "narration": 4,
            "conditionals": 4,
        },
    ),
    "B2": CEFRLevelInfo(
        level="B2",
        name="Vantage",
        description="Can interact with fluency and spontaneity, produce clear detailed text on a wide range of subjects",
        typical_skills={
            "vocabulary_recognition": 5,
            "vocabulary_production": 5,
            "pronunciation": 5,
            "grammar_receptive": 5,
            "grammar_productive": 4,
            "conversational_flow": 4,
            "cultural_pragmatics": 4,
            "narration": 5,
            "conditionals": 5,
        },
    ),
    "C1": CEFRLevelInfo(
        level="C1",
        name="Effective Operational Proficiency",
        description="Can express ideas fluently and spontaneously, use language flexibly for social and professional purposes",
        typical_skills={
            "vocabulary_recognition": 5,
            "vocabulary_production": 5,
            "pronunciation": 5,
            "grammar_receptive": 5,
            "grammar_productive": 5,
            "conversational_flow": 5,
            "cultural_pragmatics": 5,
            "narration": 5,
            "conditionals": 5,
        },
    ),
    "C2": CEFRLevelInfo(
        level="C2",
        name="Mastery",
        description="Can understand virtually everything, express meaning spontaneously with precision",
        typical_skills={
            "vocabulary_recognition": 5,
            "vocabulary_production": 5,
            "pronunciation": 5,
            "grammar_receptive": 5,
            "grammar_productive": 5,
            "conversational_flow": 5,
            "cultural_pragmatics": 5,
            "narration": 5,
            "conditionals": 5,
        },
    ),
}


def estimate_cefr_level(skills: SkillDimensions) -> str:
    """Estimate the CEFR level based on skill dimensions.

    Returns the highest CEFR level where the learner meets at least 70%
    of the typical skill requirements.
    """
    skill_dict = skills.to_dict()

    for cefr_level in reversed(CEFR_LEVELS):
        cefr_info = CEFR_DEFINITIONS[cefr_level]
        matches = 0
        total = len(cefr_info.typical_skills)

        for skill_name, required_level in cefr_info.typical_skills.items():
            if skill_dict.get(skill_name, 1) >= required_level:
                matches += 1

        if matches / total >= 0.7:
            return cefr_level

    return "A1"  # Default to A1 if no level matched


# Topic categorization for content organization
TOPICS_BY_CEFR = {
    "A1": [
        "greetings",
        "numbers",
        "basic_courtesy",
        "self_introduction",
    ],
    "A2": [
        "expressions",
        "texting",
        "fillers",
        "food",
        "transport",
        "money",
        "time",
        "weather",
    ],
    "B1": [
        "opinions",
        "feelings",
        "plans",
        "storytelling",
        "hypotheticals",
        "culture",
    ],
    "B2": [
        "abstract_topics",
        "idioms",
        "debate",
        "current_events",
    ],
}


def get_topics_for_level(cefr_level: str) -> list[str]:
    """Get all topics up to and including the given CEFR level."""
    topics = []
    for level in CEFR_LEVELS:
        topics.extend(TOPICS_BY_CEFR.get(level, []))
        if level == cefr_level:
            break
    return topics


# Content progression layers (from the plan)
CONTENT_LAYERS = {
    1: {
        "name": "Foundation",
        "cefr": "A1",
        "focus": [
            "Survival phrases: greetings, numbers 1-10, basic courtesy",
            "High-frequency vocabulary: yo, tu, es, esta, hay",
            "Present tense of ser/estar/tener",
            "Core pronunciation: vowels, basic consonants",
        ],
    },
    2: {
        "name": "Expansion",
        "cefr": "A1-A2",
        "focus": [
            "Mexican expressions",
            "Texting abbreviations",
            "Filler words for natural speech",
            "Question formation",
            "Present tense regular verbs",
        ],
    },
    3: {
        "name": "Consolidation",
        "cefr": "A2",
        "focus": [
            "Food/restaurant vocabulary and phrases",
            "Transport and directions",
            "Numbers and money",
            "Basic past tense (preterite of common verbs)",
            "Pronunciation: rr, ñ, stressed syllables",
        ],
    },
    4: {
        "name": "Independence",
        "cefr": "A2-B1",
        "focus": [
            "Extended conversations on topics of interest",
            "Expressing opinions, preferences",
            "Imperfect vs preterite",
            "Subjunctive introduction (common expressions)",
            "Regional variations awareness",
        ],
    },
    5: {
        "name": "Storytelling & Hypotheticals",
        "cefr": "B1",
        "focus": [
            "Past tense sequencing with time markers",
            "Descriptive imperfect for setting scenes",
            "Reported speech",
            "Real and hypothetical conditionals",
            "Common conditional patterns (si yo fuera, me gustaría)",
        ],
    },
    6: {
        "name": "Fluency",
        "cefr": "B1+",
        "focus": [
            "Abstract topics",
            "Idiomatic expressions and refranes",
            "Complex grammar mastery",
            "Native-like pronunciation and prosody",
        ],
    },
}


# Prompt for LLM skill assessment
SKILL_ASSESSMENT_PROMPT = """Based on this conversation exchange, assess the learner's skill level for "{skill_name}":

{level_descriptions}

Previous level: {previous_level}
Exchange:
{exchange}

What level (1-5) best describes the learner's current ability for {skill_name}?
Return just the number 1-5."""


def create_assessment_prompt(
    skill_name: str,
    previous_level: int,
    exchange: str,
) -> str:
    """Create an assessment prompt for the LLM."""
    return SKILL_ASSESSMENT_PROMPT.format(
        skill_name=skill_name,
        level_descriptions=format_level_descriptions_for_llm(skill_name),
        previous_level=previous_level,
        exchange=exchange,
    )
