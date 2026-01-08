"""PipeCat voice bot for Spanish conversation practice using OpenAI Realtime."""

import random

from pipecat.frames.frames import TranscriptionFrame, TTSTextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.services.openai.realtime.events import (
    SessionProperties,
    InputAudioTranscription,
    TurnDetection,
)
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from span.config import Config, CONVERSATION_HISTORY_LIMIT, EXTRACTION_INTERVAL
from span.curriculum.scheduler import DailyPlan
from span.db.database import Database
from span.llm.prompts import NEWS_LESSON_INSTRUCTIONS, VOICE_TUTOR_SYSTEM_PROMPT
from span.memory.extractor import MemoryExtractor
from span.voice.tools import CURRICULUM_TOOLS, register_tools

# OpenAI Realtime API voices - randomized each session for variety
# Note: fable, onyx, nova are TTS-only and NOT supported by Realtime API
OPENAI_REALTIME_VOICES = [
    "alloy", "ash", "ballad", "coral", "echo",
    "sage", "shimmer", "verse", "marin", "cedar",
]


class ConversationLogger(FrameProcessor):
    """Logs conversation transcriptions to the database for shared memory."""

    def __init__(
        self,
        db: Database,
        user_id: int,
        memory_extractor: MemoryExtractor | None = None,
    ):
        super().__init__()
        self.db = db
        self.user_id = user_id
        self.memory_extractor = memory_extractor
        self._message_count = 0
        self._recent_messages: list[dict] = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)

        # Save user transcriptions (from upstream)
        if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.UPSTREAM:
            if frame.text and frame.text.strip():
                self.db.save_message(self.user_id, "user", frame.text, "voice")
                self._recent_messages.append({"role": "user", "content": frame.text})
                self._message_count += 1

        # Save assistant responses (TTSTextFrame from downstream)
        if isinstance(frame, TTSTextFrame) and direction == FrameDirection.DOWNSTREAM:
            if frame.text and frame.text.strip():
                self.db.save_message(self.user_id, "assistant", frame.text, "voice")
                self._recent_messages.append({"role": "assistant", "content": frame.text})

                # Trigger extraction after every N message pairs
                if self.memory_extractor and self._message_count >= EXTRACTION_INTERVAL:
                    self._message_count = 0
                    # Get last few messages for extraction (don't block pipeline)
                    # Create a copy to avoid race condition with async extraction
                    messages_to_extract = [dict(m) for m in self._recent_messages[-8:]]
                    self._recent_messages = self._recent_messages[-4:]  # Keep some context
                    self.memory_extractor.schedule_extraction(
                        self.user_id, messages_to_extract, "voice"
                    )

        await self.push_frame(frame, direction)


class SpanishTutorBot:
    """Voice bot for Spanish conversation practice using OpenAI Realtime.

    Uses OpenAI's gpt-realtime model which provides:
    - Native speech understanding (no separate STT needed)
    - Built-in pronunciation assessment
    - Natural Spanish voice output (no separate TTS needed)
    - Low-latency conversational responses
    - Function calling for curriculum integration
    """

    def __init__(
        self,
        config: Config,
        lesson_plan: DailyPlan | None = None,
        db: Database | None = None,
        user_id: int = 1,
        is_news_lesson: bool = False,
    ):
        self.config = config
        self.lesson_plan = lesson_plan
        self.db = db
        self.user_id = user_id
        self.is_news_lesson = is_news_lesson
        self._llm = None
        self._tool_handlers = None
        self.memory_extractor = None
        if db and config.anthropic_api_key:
            self.memory_extractor = MemoryExtractor(db, config.anthropic_api_key)

    def build_system_prompt(self) -> str:
        """Build the system prompt for the voice tutor."""
        if not self.lesson_plan:
            base_prompt = VOICE_TUTOR_SYSTEM_PROMPT.format(
                topic="general conversation",
                vocabulary="common greetings and expressions",
                new_vocabulary="none",
            )
        else:
            review_vocab = [item.spanish for item in self.lesson_plan.review_items[:5]]
            new_vocab = [item.spanish for item in self.lesson_plan.new_items]

            base_prompt = VOICE_TUTOR_SYSTEM_PROMPT.format(
                topic=self.lesson_plan.suggested_topic,
                vocabulary=", ".join(review_vocab) if review_vocab else "none",
                new_vocabulary=", ".join(new_vocab) if new_vocab else "none",
            )

        # Add learner profile context if available
        if self.db:
            profile = self.db.get_or_create_learner_profile(self.user_id)
            learner_context = profile.to_context_block()
            if learner_context:
                base_prompt = f"{base_prompt}\n\n## About This Learner\n{learner_context}"

            # Add current skill levels for informed assessment
            from span.constants import SKILL_NAMES
            from span.db.models import SkillLevel

            skills = self.db.get_or_create_skill_dimensions(self.user_id)
            skill_lines = []
            for name in SKILL_NAMES:
                level = getattr(skills, name, 1)
                skill_lines.append(f"- {name}: {level} ({SkillLevel(level).name})")

            skill_context = f"""
## Current Skill Levels
{chr(10).join(skill_lines)}

When calling record_practice, consider the quality score based on these skill levels.
Use skill_observations parameter to report specific skill demonstrations you observe.
"""
            base_prompt = f"{base_prompt}\n{skill_context}"

        # Add news lesson instructions if this is a news-based session
        if self.is_news_lesson:
            base_prompt = f"{base_prompt}\n{NEWS_LESSON_INSTRUCTIONS}"

        return base_prompt

    def create_llm_service(self) -> OpenAIRealtimeLLMService:
        """Create the OpenAI Realtime service for speech-to-speech conversation."""
        system_prompt = self.build_system_prompt()

        # Randomize voice each session for variety
        voice = random.choice(OPENAI_REALTIME_VOICES)

        session_properties = SessionProperties(
            input_audio_transcription=InputAudioTranscription(model="whisper-1"),
            turn_detection=TurnDetection(type="server_vad"),
            instructions=system_prompt,
            voice=voice,
        )

        self._llm = OpenAIRealtimeLLMService(
            api_key=self.config.openai_api_key,
            model="gpt-realtime-2025-08-28",
            session_properties=session_properties,
        )

        # Register tool handlers if database is available
        if self.db:
            self._tool_handlers = register_tools(
                self._llm, self.db, self.user_id, self.config, self.is_news_lesson
            )

        return self._llm

    def create_transport(self, room_url: str, token: str) -> DailyTransport:
        """Create the Daily transport for voice calls."""
        return DailyTransport(
            room_url,
            token,
            "Spanish Tutor",
            DailyParams(
                api_key=self.config.daily_api_key,
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_enabled=True,
                vad_analyzer=None,  # Use default
                transcription_enabled=False,  # OpenAI Realtime handles this
            ),
        )

    def create_context(self) -> OpenAILLMContext:
        """Create the LLM context with tools and conversation history."""
        messages = []

        # Load shared conversation history from database
        if self.db:
            history = self.db.get_conversation_history(self.user_id, limit=CONVERSATION_HISTORY_LIMIT)
            for msg in history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Add initial greeting if no history
        if not messages:
            messages.append({
                "role": "assistant",
                "content": "¡Hola! ¿Qué onda? ¿Cómo estás hoy?",
            })

        # Include tools in context if database is available
        if self.db:
            return OpenAILLMContext(messages=messages, tools=CURRICULUM_TOOLS)
        return OpenAILLMContext(messages=messages)

    async def create_pipeline(self, transport: DailyTransport) -> Pipeline:
        """Create the PipeCat pipeline for voice conversation.

        With OpenAI Realtime, the pipeline is much simpler:
        - No separate STT service (speech is processed directly)
        - No separate TTS service (speech is generated directly)
        - Single service handles the entire conversation
        - Tools enable curriculum tracking and hints
        - ConversationLogger saves transcripts for shared memory with Telegram
        """
        llm = self.create_llm_service()
        context = self.create_context()
        context_aggregator = llm.create_context_aggregator(context)

        # Build pipeline components
        pipeline_components = [
            transport.input(),
            context_aggregator.user(),
            llm,
            transport.output(),
            context_aggregator.assistant(),
        ]

        # Add conversation logger for shared memory if database available
        if self.db:
            logger = ConversationLogger(self.db, self.user_id, self.memory_extractor)
            # Insert logger after LLM to capture both directions
            pipeline_components.insert(3, logger)

        pipeline = Pipeline(pipeline_components)

        return pipeline

    def get_pipeline_params(self) -> PipelineParams:
        """Get pipeline parameters."""
        return PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        )
