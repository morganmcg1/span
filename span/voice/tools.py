"""Tool definitions and handlers for the voice bot curriculum integration.

Includes skill dimension tracking based on the adaptive curriculum framework.
"""

import asyncio
import json
from datetime import datetime

from anthropic import Anthropic
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema

from span.config import Config
from span.constants import VALID_SKILLS
from span.curriculum.sm2 import calculate_sm2
from span.curriculum.selector import should_advance_skill
from span.db.database import Database
from span.db.models import LessonSession, LessonType, SkillDimensions


# Tool schema definitions
CURRICULUM_TOOLS = ToolsSchema(
    standard_tools=[
        FunctionSchema(
            name="record_practice",
            description="Record that the student practiced a vocabulary item. Call this after practicing each word to track their progress.",
            properties={
                "spanish_word": {
                    "type": "string",
                    "description": "The Spanish word or phrase that was practiced",
                },
                "quality": {
                    "type": "integer",
                    "description": "How well they did: 5=perfect no hesitation, 4=correct with hesitation, 3=correct with difficulty, 2=incorrect but close, 1=incorrect, 0=no attempt",
                },
                "pronunciation_score": {
                    "type": "integer",
                    "description": "Pronunciation quality 1-5, or omit if not assessed",
                },
                "skill_observations": {
                    "type": "object",
                    "description": "Optional skill-level observations based on this response. Keys are skill names (vocabulary_production, pronunciation, grammar_productive, conversational_flow, cultural_pragmatics, narration, conditionals), values are observed levels 1-5 (1=none, 2=exposure, 3=recognition, 4=production, 5=fluent). Only include skills you clearly observed.",
                },
            },
            required=["spanish_word", "quality"],
        ),
        FunctionSchema(
            name="get_hint",
            description="Get a hint for a vocabulary item when the student is struggling to remember it",
            properties={
                "spanish_word": {
                    "type": "string",
                    "description": "The word or phrase they need help with",
                },
            },
            required=["spanish_word"],
        ),
        FunctionSchema(
            name="get_curriculum_advice",
            description="Ask the curriculum advisor for guidance on what to do next when you need help deciding",
            properties={
                "situation": {
                    "type": "string",
                    "description": "Describe what's happening: student struggling, doing well, bored, confused, etc.",
                },
                "question": {
                    "type": "string",
                    "description": "What advice do you need? Be specific.",
                },
            },
            required=["situation", "question"],
        ),
        FunctionSchema(
            name="end_lesson_summary",
            description="End the lesson and save a summary. Call this when wrapping up the conversation.",
            properties={
                "words_practiced": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Spanish words/phrases practiced during the lesson",
                },
                "overall_performance": {
                    "type": "string",
                    "enum": ["excellent", "good", "needs_work"],
                    "description": "Overall assessment of the student's performance",
                },
                "notes": {
                    "type": "string",
                    "description": "Any observations about the lesson, pronunciation progress, areas to focus on",
                },
            },
            required=["words_practiced", "overall_performance"],
        ),
    ]
)


CURRICULUM_ADVISOR_PROMPT = """You are a curriculum advisor for a Mexican Spanish language learning app.
Your role is to help the voice tutor (Lupita) make decisions about the lesson flow.

The student is practicing conversational Mexican Spanish via phone calls.
The tutor uses spaced repetition (SM-2) to schedule vocabulary review.

When asked for advice, consider:
1. Student engagement - are they bored, frustrated, or excited?
2. Learning progression - should we introduce new words or focus on review?
3. Difficulty adjustment - should we make things easier or more challenging?
4. Session pacing - how much time is left and what should we prioritize?

Respond with a brief, actionable suggestion (2-3 sentences max)."""


class CurriculumToolHandlers:
    """Handlers for curriculum-related tool calls from the voice bot.

    Tracks both SM-2 spaced repetition and skill dimension updates.
    """

    def __init__(self, db: Database, user_id: int, config: Config):
        self.db = db
        self.user_id = user_id
        self.config = config
        self.anthropic = Anthropic(api_key=config.anthropic_api_key)
        self.session_start = datetime.now()
        self.practice_records: list[dict] = []
        # Track consecutive correct per skill for advancement
        self.skill_streak: dict[str, int] = {}
        # Load current skill dimensions
        self.skills = self.db.get_or_create_skill_dimensions(user_id)

    def _update_skill_dimensions(
        self,
        item_contributions: dict[str, int],
        quality: int,
        response_time_ms: int | None = None,
    ) -> dict[str, int]:
        """Update skill dimensions based on practice performance.

        Returns dict of skills that advanced.
        """
        advanced_skills = {}

        for skill_name, target_level in item_contributions.items():
            current_level = getattr(self.skills, skill_name, 1)

            # Track streaks per skill
            if skill_name not in self.skill_streak:
                self.skill_streak[skill_name] = 0

            if quality >= 3:  # Correct response
                self.skill_streak[skill_name] += 1
            else:
                self.skill_streak[skill_name] = 0

            # Check if skill should advance
            if should_advance_skill(
                consecutive_correct=self.skill_streak[skill_name],
                response_time_ms=response_time_ms,
                current_level=current_level,
            ):
                # Only advance up to the item's contribution level
                new_level = min(current_level + 1, target_level)
                if new_level > current_level:
                    setattr(self.skills, skill_name, new_level)
                    advanced_skills[skill_name] = new_level
                    # Reset streak after advancement
                    self.skill_streak[skill_name] = 0

        # Save updated skills if any changed
        if advanced_skills:
            self.db.update_skill_dimensions(self.skills)

        return advanced_skills

    async def record_practice(self, params) -> None:
        """Record vocabulary practice and update SM-2 progress + skill dimensions."""
        args = params.arguments
        spanish_word = args.get("spanish_word", "").strip()
        quality = args.get("quality", 3)
        pronunciation_score = args.get("pronunciation_score")
        skill_observations = args.get("skill_observations", {})

        # Validate inputs
        if not spanish_word:
            await params.result_callback({
                "status": "error",
                "message": "spanish_word is required",
            })
            return

        # Clamp quality to valid range 0-5
        quality = max(0, min(5, int(quality)))

        # Look up the curriculum item
        item = self.db.get_curriculum_item_by_spanish(spanish_word)
        if not item:
            await params.result_callback({
                "status": "not_found",
                "message": f"Word '{spanish_word}' not in curriculum",
            })
            return

        # Get or create progress for this item
        progress = self.db.get_or_create_progress(self.user_id, item.id)

        # Calculate new SM-2 values
        sm2_result = calculate_sm2(
            quality=quality,
            easiness_factor=progress.easiness_factor,
            interval_days=progress.interval_days,
            repetitions=progress.repetitions,
        )

        # Update progress
        progress.easiness_factor = sm2_result.easiness_factor
        progress.interval_days = sm2_result.interval_days
        progress.repetitions = sm2_result.repetitions
        progress.next_review = sm2_result.next_review
        progress.last_reviewed = datetime.now()
        self.db.update_progress(progress)

        # Merge item contributions with LLM skill observations
        # LLM observations can provide additional context beyond item's default contributions
        effective_contributions = dict(item.skill_contributions) if item.skill_contributions else {}

        # Merge LLM observations - they can add skills not in item.skill_contributions
        # or provide higher targets if the LLM observed stronger performance
        if skill_observations and isinstance(skill_observations, dict):
            for skill_name, observed_level in skill_observations.items():
                if skill_name in VALID_SKILLS:
                    # Clamp to valid range 1-5
                    observed_level = max(1, min(5, int(observed_level)))
                    # Use the higher of item contribution or LLM observation
                    current_target = effective_contributions.get(skill_name, 0)
                    effective_contributions[skill_name] = max(current_target, observed_level)

        # Update skill dimensions based on merged contributions
        advanced_skills = {}
        if effective_contributions:
            advanced_skills = self._update_skill_dimensions(
                item_contributions=effective_contributions,
                quality=quality,
                response_time_ms=None,  # Could add response time tracking
            )

        # Track for session summary
        self.practice_records.append({
            "word": spanish_word,
            "quality": quality,
            "pronunciation_score": pronunciation_score,
            "next_review_days": sm2_result.interval_days,
            "skills_advanced": advanced_skills,
        })

        # Build response message
        message = f"Progress saved. Next review in {sm2_result.interval_days} day(s)."
        if advanced_skills:
            skill_names = ", ".join(advanced_skills.keys())
            message += f" Skills improved: {skill_names}!"

        await params.result_callback({
            "status": "recorded",
            "word": spanish_word,
            "quality": quality,
            "next_review_days": sm2_result.interval_days,
            "skills_advanced": advanced_skills,
            "message": message,
        })

    async def get_hint(self, params) -> None:
        """Get hint for a vocabulary item."""
        args = params.arguments
        spanish_word = args.get("spanish_word", "").strip()

        if not spanish_word:
            await params.result_callback({
                "found": False,
                "message": "spanish_word is required",
            })
            return

        item = self.db.get_curriculum_item_by_spanish(spanish_word)
        if not item:
            # Try to find a close match
            all_items = self.db.get_all_curriculum_items()
            close_matches = [
                i for i in all_items
                if spanish_word.lower() in i.spanish.lower() or i.spanish.lower() in spanish_word.lower()
            ]
            if close_matches:
                item = close_matches[0]
            else:
                await params.result_callback({
                    "found": False,
                    "message": f"Word '{spanish_word}' not found in curriculum",
                })
                return

        await params.result_callback({
            "found": True,
            "spanish": item.spanish,
            "english": item.english,
            "example": item.example_sentence,
            "mexican_notes": item.mexican_notes,
            "topic": item.topic,
        })

    async def get_curriculum_advice(self, params) -> None:
        """Get curriculum advice from Claude."""
        args = params.arguments
        situation = args["situation"]
        question = args["question"]

        # Build context about current session
        session_minutes = (datetime.now() - self.session_start).seconds // 60
        words_practiced = len(self.practice_records)
        avg_quality = (
            sum(r["quality"] for r in self.practice_records) / words_practiced
            if words_practiced > 0
            else None
        )

        avg_display = f"{avg_quality:.1f}" if avg_quality else "N/A"
        context = f"""Current session:
- Duration: {session_minutes} minutes
- Words practiced: {words_practiced}
- Average quality score: {avg_display}
- Recent practice: {[r['word'] for r in self.practice_records[-5:]]}

        Situation: {situation}
        Question: {question}"""

        # Anthropic client is synchronous; avoid blocking the voice event loop.
        response = await asyncio.to_thread(
            self.anthropic.messages.create,
            model=self.config.claude_model,
            max_tokens=200,
            system=CURRICULUM_ADVISOR_PROMPT,
            messages=[{"role": "user", "content": context}],
        )

        advice = response.content[0].text
        await params.result_callback({
            "advice": advice,
            "session_minutes": session_minutes,
            "words_practiced": words_practiced,
        })

    async def end_lesson_summary(self, params) -> None:
        """End lesson and save session summary with skill progression."""
        args = params.arguments
        words_practiced = args["words_practiced"]
        overall_performance = args["overall_performance"]
        notes = args.get("notes", "")

        # Calculate session duration
        duration_seconds = (datetime.now() - self.session_start).seconds

        # Map performance to score
        performance_scores = {"excellent": 1.0, "good": 0.7, "needs_work": 0.4}
        score = performance_scores.get(overall_performance, 0.5)

        # Collect all skills that advanced during the session
        all_advanced_skills = {}
        for record in self.practice_records:
            for skill, level in record.get("skills_advanced", {}).items():
                all_advanced_skills[skill] = level

        # Add skill progression to notes
        if all_advanced_skills:
            skill_progress = ", ".join(f"{k}: level {v}" for k, v in all_advanced_skills.items())
            notes = f"{notes}\nSkills improved: {skill_progress}".strip()

        # Create session record
        session = LessonSession(
            user_id=self.user_id,
            lesson_type=LessonType.VOICE_CONVERSATION,
            topic="practice",
            items_covered=json.dumps(words_practiced),
            performance_score=score,
            duration_seconds=duration_seconds,
            notes=notes,
        )
        session_id = self.db.create_session(session)

        # Build response message
        message = f"Lesson saved! {len(words_practiced)} words practiced in {duration_seconds // 60} minutes."
        if all_advanced_skills:
            message += f" {len(all_advanced_skills)} skill(s) improved!"

        await params.result_callback({
            "status": "saved",
            "session_id": session_id,
            "duration_minutes": duration_seconds // 60,
            "words_count": len(words_practiced),
            "performance": overall_performance,
            "skills_advanced": all_advanced_skills,
            "current_skills": self.skills.to_dict(),
            "message": message,
        })


def register_tools(llm, db: Database, user_id: int, config: Config) -> CurriculumToolHandlers:
    """Register curriculum tools with the LLM service."""
    handlers = CurriculumToolHandlers(db, user_id, config)

    llm.register_function("record_practice", handlers.record_practice)
    llm.register_function("get_hint", handlers.get_hint)
    llm.register_function("get_curriculum_advice", handlers.get_curriculum_advice)
    llm.register_function("end_lesson_summary", handlers.end_lesson_summary)

    return handlers
