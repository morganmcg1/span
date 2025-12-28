"""Async fact extraction service for continuous memory updates.

Extracts both learner profile facts and skill level indicators from conversation.
Uses categorical skill levels (1-5) that are LLM-friendly for assessment.
"""

import asyncio
import json
import logging
from dataclasses import dataclass

from anthropic import Anthropic

from span.constants import VALID_SKILLS
from span.db.database import Database
from span.db.models import LearnerProfile, SkillDimensions, SkillLevel

logger = logging.getLogger(__name__)


# Skill level descriptions for LLM assessment
SKILL_LEVEL_GUIDE = """
Skill levels (1-5):
1-NONE: No exposure - cannot recognize or produce
2-EXPOSURE: Has seen/heard - may recognize with strong hints
3-RECOGNITION: Can understand when heard/read - cannot produce reliably
4-PRODUCTION: Can produce with effort - needs time or makes minor errors
5-FLUENT: Automatic - produces quickly and accurately
"""


EXTRACTION_PROMPT = """Analyze this conversation snippet and extract any new facts about the learner.

<conversation>
{conversation}
</conversation>

<current_profile>
{current_profile}
</current_profile>

<current_skills>
{current_skills}
</current_skills>

{skill_level_guide}

Extract ONLY NEW information not already in the profile. Return a JSON object with these fields (omit fields if no new info):

{{
  "name": "learner's name if mentioned",
  "location": "where they're from if mentioned",
  "interests": ["new interests mentioned"],
  "goals": ["new learning goals mentioned"],
  "strengths": ["topics/skills they showed proficiency in"],
  "weaknesses": ["topics/skills they struggled with"],
  "milestones": ["achievements like 'mastered qué onda'"],
  "level_change": "beginner|intermediate|advanced if level should change",
  "notes": "any other relevant observations",

  "skill_updates": {{
    "vocabulary_recognition": 3,
    "vocabulary_production": 2,
    "pronunciation": 2,
    "grammar_receptive": 3,
    "grammar_productive": 2,
    "conversational_flow": 2,
    "cultural_pragmatics": 2,
    "narration": 1,
    "conditionals": 1
  }}
}}

For skill_updates:
- Only include skills where you observed clear evidence of ability in THIS conversation
- Use the 1-5 scale based on what you observed
- Only update a skill if the observed level is HIGHER than the current level shown above
- Be conservative - only mark PRODUCTION (4) or FLUENT (5) if they produced Spanish correctly and naturally

Be conservative - only extract clear, explicit facts. Return empty {{}} if nothing new.
"""


@dataclass
class ExtractionResult:
    """Result of fact extraction."""

    facts_extracted: int = 0
    profile_updated: bool = False
    skills_updated: dict[str, int] = None  # Skills that were advanced
    milestones: list[str] = None

    def __post_init__(self):
        if self.milestones is None:
            self.milestones = []
        if self.skills_updated is None:
            self.skills_updated = {}


class MemoryExtractor:
    """Extracts facts from conversations and updates learner profiles."""

    def __init__(self, db: Database, anthropic_api_key: str):
        self.db = db
        self.client = Anthropic(api_key=anthropic_api_key)
        self._extraction_lock = asyncio.Lock()

    async def extract_facts_async(
        self,
        user_id: int,
        messages: list[dict],
        channel: str = "unknown",
    ) -> ExtractionResult:
        """Extract facts from recent messages in background.

        Args:
            user_id: User to extract facts for
            messages: Recent conversation messages [{"role": "...", "content": "..."}]
            channel: Source channel (telegram, voice)

        Returns:
            ExtractionResult with details of what was extracted
        """
        if not messages:
            return ExtractionResult()

        # Get current profile and skills
        profile = self.db.get_or_create_learner_profile(user_id)
        skills = self.db.get_or_create_skill_dimensions(user_id)

        # Format conversation
        conversation_text = "\n".join(
            f"{msg['role'].title()}: {msg['content']}"
            for msg in messages
        )

        # Format current skills for context
        skills_text = "\n".join(
            f"- {name}: {level} ({SkillLevel(level).name})"
            for name, level in skills.to_dict().items()
            if name not in ("id", "user_id", "updated_at", "created_at")
        )

        # Call Claude for extraction (use Sonnet for speed/cost)
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=700,
                messages=[{
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(
                        conversation=conversation_text,
                        current_profile=profile.to_context_block(),
                        current_skills=skills_text,
                        skill_level_guide=SKILL_LEVEL_GUIDE,
                    )
                }],
            )

            # Parse response
            response_text = response.content[0].text.strip()

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            extracted = json.loads(response_text)

        except (json.JSONDecodeError, IndexError, KeyError):
            # Extraction failed, return empty result
            return ExtractionResult()

        if not extracted:
            return ExtractionResult()

        # Update profile with extracted facts
        result = ExtractionResult()
        profile_changed = False

        async with self._extraction_lock:
            # Refresh profile in case it changed
            profile = self.db.get_or_create_learner_profile(user_id)

            if extracted.get("name") and not profile.name:
                profile.name = extracted["name"]
                profile_changed = True
                result.facts_extracted += 1

            if extracted.get("location") and not profile.location:
                profile.location = extracted["location"]
                profile_changed = True
                result.facts_extracted += 1

            # Append to lists (avoiding duplicates)
            for interest in extracted.get("interests", []):
                if interest and interest not in profile.interests:
                    profile.interests.append(interest)
                    profile_changed = True
                    result.facts_extracted += 1

            for goal in extracted.get("goals", []):
                if goal and goal not in profile.goals:
                    profile.goals.append(goal)
                    profile_changed = True
                    result.facts_extracted += 1

            for strength in extracted.get("strengths", []):
                if strength and strength not in profile.strong_topics:
                    profile.strong_topics.append(strength)
                    profile_changed = True
                    result.facts_extracted += 1

            for weakness in extracted.get("weaknesses", []):
                if weakness and weakness not in profile.weak_topics:
                    profile.weak_topics.append(weakness)
                    profile_changed = True
                    result.facts_extracted += 1

            if extracted.get("level_change"):
                new_level = extracted["level_change"]
                if new_level in ("beginner", "intermediate", "advanced"):
                    if new_level != profile.level:
                        profile.level = new_level
                        profile_changed = True
                        result.facts_extracted += 1

            if extracted.get("notes"):
                if profile.notes:
                    profile.notes += f"\n{extracted['notes']}"
                else:
                    profile.notes = extracted["notes"]
                profile_changed = True

            # Save milestones as extracted facts
            for milestone in extracted.get("milestones", []):
                if milestone:
                    self.db.save_extracted_fact(
                        user_id=user_id,
                        fact_type="milestone",
                        fact_value=milestone,
                        source_channel=channel,
                    )
                    result.milestones.append(milestone)
                    result.facts_extracted += 1

            # Save profile if changed
            if profile_changed:
                self.db.update_learner_profile(profile)
                result.profile_updated = True

            # Process skill updates
            skill_updates = extracted.get("skill_updates", {})
            if skill_updates:
                # Refresh skills in case they changed
                skills = self.db.get_or_create_skill_dimensions(user_id)
                skills_changed = False

                for skill_name, observed_level in skill_updates.items():
                    if skill_name not in VALID_SKILLS:
                        continue

                    # Clamp to valid range
                    observed_level = max(1, min(5, int(observed_level)))

                    # Only update if observed level is higher
                    current_level = getattr(skills, skill_name, 1)
                    if observed_level > current_level:
                        setattr(skills, skill_name, observed_level)
                        result.skills_updated[skill_name] = observed_level
                        skills_changed = True
                        result.facts_extracted += 1
                        logger.info(
                            f"Skill {skill_name} advanced: {current_level} -> {observed_level} "
                            f"for user {user_id}"
                        )

                if skills_changed:
                    self.db.update_skill_dimensions(skills)

        return result

    def schedule_extraction(
        self,
        user_id: int,
        messages: list[dict],
        channel: str = "unknown",
    ) -> asyncio.Task:
        """Schedule fact extraction to run in background.

        Returns the task so caller can optionally await it.
        """
        task = asyncio.create_task(
            self.extract_facts_async(user_id, messages, channel)
        )

        def _handle_extraction_error(t: asyncio.Task) -> None:
            """Log any exceptions from background extraction."""
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(f"Background fact extraction failed for user {user_id}: {exc}")

        task.add_done_callback(_handle_extraction_error)
        return task
