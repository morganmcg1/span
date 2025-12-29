"""Telegram bot for Spanish practice via text and voice notes."""

import asyncio
import os
import tempfile
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from rich.console import Console

from span.config import Config, CONVERSATION_HISTORY_LIMIT, EXTRACTION_INTERVAL
from span.curriculum.scheduler import CurriculumScheduler
from span.db.database import Database
from span.db.models import CurriculumItem, User
from span.llm.client import ClaudeClient, ChatResponse, Message as LLMMessage
from span.llm.prompts import TELEGRAM_TUTOR_SYSTEM_PROMPT, VOICE_NOTE_TUTOR_PROMPT
from span.memory.extractor import MemoryExtractor
from span.telegram.voice_handler import RealtimeVoiceClient


console = Console()


class SpanTelegramBot:
    """Telegram bot for Spanish text practice."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.bot = Bot(token=config.telegram_bot_token)
        self.dp = Dispatcher()
        self.llm = ClaudeClient(config.anthropic_api_key, config.claude_model)
        self.scheduler = CurriculumScheduler(db)
        self.memory_extractor = MemoryExtractor(db, config.anthropic_api_key)
        self._message_count: dict[int, int] = {}  # user_id -> message count
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register message handlers."""

        @self.dp.message(Command("start"))
        async def start_handler(message: Message) -> None:
            """Handle /start command."""
            _user = self._ensure_user(message.from_user.id)  # Ensure user exists

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🆕 New words", callback_data="cmd_new"),
                    InlineKeyboardButton(text="📚 Review", callback_data="cmd_review"),
                ],
                [
                    InlineKeyboardButton(text="🚀 ¡Vamos!", callback_data="cmd_v"),
                    InlineKeyboardButton(text="🎤 Voice chat", callback_data="cmd_chat"),
                ],
                [
                    InlineKeyboardButton(text="📖 Vocab", callback_data="cmd_vocab"),
                    InlineKeyboardButton(text="📊 Stats", callback_data="cmd_stats"),
                ],
            ])

            await message.answer(
                "¡Hola! 👋 I'm your Mexican Spanish tutor.\n\n"
                "Text me anytime to practice, or send voice notes for pronunciation feedback!\n\n"
                "*Quick actions:*",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

        @self.dp.message(Command("review"))
        async def review_handler(message: Message) -> None:
            """Send items due for review."""
            user = self._ensure_user(message.from_user.id)
            if not user:
                await message.answer("Error: Could not find your user profile.")
                return

            items = self.scheduler.get_items_due_for_review(user.id, limit=5)

            if not items:
                await message.answer(
                    "¡Muy bien! No items due for review right now. 🎉\n"
                    "Use /new to learn something new!"
                )
                return

            await message.answer(f"📚 *{len(items)} items to review:*", parse_mode="Markdown")

            for item in items:
                text = f"**{item.spanish}**\n_{item.english}_"
                if item.example_sentence:
                    text += f"\n\nExample: {item.example_sentence}"
                if item.mexican_notes:
                    text += f"\n\n💡 {item.mexican_notes}"
                await message.answer(text, parse_mode="Markdown")
                await asyncio.sleep(0.5)  # Avoid rate limiting

        @self.dp.message(Command("new"))
        async def new_handler(message: Message) -> None:
            """Introduce new vocabulary."""
            user = self._ensure_user(message.from_user.id)
            if not user:
                await message.answer("Error: Could not find your user profile.")
                return

            items = self.scheduler.get_new_items(user.id, count=3)

            if not items:
                await message.answer(
                    "You've seen all the vocabulary! 🏆\n"
                    "More content coming soon."
                )
                return

            await message.answer(f"🆕 *{len(items)} new words to learn:*", parse_mode="Markdown")

            for item in items:
                # Create progress entry for this item
                self.db.get_or_create_progress(user.id, item.id)

                text = f"**{item.spanish}** = {item.english}"
                if item.example_sentence:
                    text += f"\n\n📝 {item.example_sentence}"
                if item.mexican_notes:
                    text += f"\n\n💡 {item.mexican_notes}"
                await message.answer(text, parse_mode="Markdown")
                await asyncio.sleep(0.5)

            await message.answer(
                "Try using these in a sentence! Just reply with your practice."
            )

        @self.dp.message(Command("v"))
        async def v_handler(message: Message) -> None:
            """Start a practice conversation."""
            user = self._ensure_user(message.from_user.id)
            if not user:
                await message.answer("Error: Could not find your user profile.")
                return

            plan = self.scheduler.create_daily_plan(user.id)
            vocab = [item.spanish for item in (plan.review_items + plan.new_items)[:5]]

            starter = self.llm.generate_conversation_prompt(
                topic=plan.suggested_topic,
                vocabulary=vocab,
            )

            await message.answer(
                f"Let's practice! Topic: *{plan.suggested_topic}*\n\n{starter}",
                parse_mode="Markdown",
            )

        @self.dp.message(Command("stats"))
        async def stats_handler(message: Message) -> None:
            """Show user progress stats."""
            user = self._ensure_user(message.from_user.id)
            if not user:
                await message.answer("Error: Could not find your user profile.")
                return

            sessions = self.db.get_recent_sessions(user.id, limit=10)
            review_items = self.scheduler.get_items_due_for_review(user.id, limit=100)
            new_items = self.scheduler.get_new_items(user.id, count=100)

            total_sessions = len(sessions)
            items_learning = 100 - len(new_items)  # Rough estimate
            items_due = len(review_items)

            await message.answer(
                f"📊 *Your Progress*\n\n"
                f"Sessions completed: {total_sessions}\n"
                f"Items learning: ~{items_learning}\n"
                f"Items due for review: {items_due}\n\n"
                f"Keep practicing! 💪",
                parse_mode="Markdown",
            )

        @self.dp.message(Command("vocab"))
        async def vocab_handler(message: Message) -> None:
            """Show vocabulary list for quick reference."""
            user = self._ensure_user(message.from_user.id)
            if not user:
                await message.answer("Error: Could not find your user profile.")
                return

            # Get items the user is currently learning (has progress on)
            items = self.db.get_user_vocabulary(user.id, limit=20)

            if not items:
                await message.answer(
                    "No vocabulary yet! Use /new to start learning."
                )
                return

            # Build compact list for easy phone scrolling
            text = "📖 *Your Vocabulary*\n\n"
            for item in items:
                text += f"• **{item.spanish}** — {item.english}\n"

            text += f"\n_{len(items)} words_ • /review for practice"

            await message.answer(text, parse_mode="Markdown")

        @self.dp.message(Command("chat"))
        async def chat_handler(message: Message) -> None:
            """Start a voice chat session via browser."""
            _user = self._ensure_user(message.from_user.id)

            await message.answer("Starting voice room... one moment!")

            # Call the voice server to create a room
            voice_server_url = f"http://localhost:{self.config.voice_server_port}/web"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(voice_server_url) as resp:
                        if resp.status != 200:
                            await message.answer(
                                "Could not start voice room. Is the voice server running?\n"
                                f"Start it with: `uv run python -m span.voice`",
                                parse_mode="Markdown",
                            )
                            return

                        data = await resp.json()

                        if "error" in data:
                            await message.answer(f"Error: {data['error']}")
                            return

                        room_url = data.get("room_url")
                        if room_url:
                            await message.answer(
                                f"Voice room ready!\n\n"
                                f"Open this link in your browser and allow mic access:\n"
                                f"{room_url}",
                            )
                        else:
                            await message.answer("Error: No room URL returned")

            except aiohttp.ClientConnectorError:
                await message.answer(
                    "Could not connect to voice server.\n"
                    "Start it with: `uv run python -m span.voice`",
                    parse_mode="Markdown",
                )

        # Button callback handlers for menu commands
        @self.dp.callback_query(F.data.startswith("cmd_"))
        async def menu_button_callback(callback: CallbackQuery) -> None:
            """Handle menu button presses by dispatching to command handlers."""
            cmd = callback.data.replace("cmd_", "")
            await callback.answer()  # Dismiss the loading state

            handlers = {
                "new": new_handler,
                "review": review_handler,
                "v": v_handler,
                "chat": chat_handler,
                "vocab": vocab_handler,
                "stats": stats_handler,
            }

            if cmd in handlers:
                await handlers[cmd](callback.message)

        # Button callback handlers for AI-generated options
        @self.dp.callback_query(F.data.startswith("ai_"))
        async def ai_button_callback(callback: CallbackQuery) -> None:
            """Handle AI-generated button presses by sending the value as a message."""
            value = callback.data.replace("ai_", "")
            await callback.answer()  # Dismiss the loading state

            # Show what was selected
            await callback.message.edit_reply_markup(reply_markup=None)  # Remove buttons

            # Create a synthetic message-like object to process the button value
            user = self._ensure_user(callback.from_user.id)
            if not user:
                await callback.message.answer("Error: Could not find your user profile.")
                return

            try:
                # Get learner profile for personalized context
                profile = self.db.get_or_create_learner_profile(user.id)

                # Get current plan for context
                plan = self.scheduler.create_daily_plan(user.id)
                practice_focus = plan.voice_lesson_focus or "General conversation"

                # Load conversation history
                history = self.db.get_conversation_history(user.id, limit=CONVERSATION_HISTORY_LIMIT)
                messages = [
                    LLMMessage(role=msg.role, content=msg.content)
                    for msg in history
                ]
                # Add button selection as user message
                messages.append(LLMMessage(role="user", content=value))

                # Build system prompt
                learner_context = profile.to_context_block()
                system = TELEGRAM_TUTOR_SYSTEM_PROMPT.format(practice_focus=practice_focus)
                if learner_context:
                    system = f"{system}\n\n## About This Learner\n{learner_context}"

                chat_response = self.llm.chat_with_buttons(
                    messages=messages,
                    system=system,
                    max_tokens=300,
                )

                # Save messages
                self.db.save_message(user.id, "user", f"[Selected: {value}]", "telegram")
                self.db.save_message(user.id, "assistant", chat_response.text, "telegram")

                # Reply with optional buttons
                if chat_response.buttons:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=btn.label,
                            callback_data=f"ai_{btn.value[:50]}",
                        )]
                        for btn in chat_response.buttons[:4]
                    ])
                    await callback.message.answer(chat_response.text, reply_markup=keyboard)
                else:
                    await callback.message.answer(chat_response.text)

            except Exception as e:
                console.print(f"[red]AI button callback error: {e}[/red]")
                await callback.message.answer(self._format_error(e, "text"))

        @self.dp.message(F.text)
        async def text_handler(message: Message) -> None:
            """Handle free-form text practice with shared conversation history."""
            user = self._ensure_user(message.from_user.id)
            if not user:
                await message.answer("Error: Could not find your user profile.")
                return

            try:
                # Get learner profile for personalized context
                profile = self.db.get_or_create_learner_profile(user.id)

                # Get current plan for context
                plan = self.scheduler.create_daily_plan(user.id)
                practice_focus = plan.voice_lesson_focus or "General conversation"

                # Load conversation history (shared across voice and telegram)
                history = self.db.get_conversation_history(user.id, limit=CONVERSATION_HISTORY_LIMIT)
                messages = [
                    LLMMessage(role=msg.role, content=msg.content)
                    for msg in history
                ]
                # Add current message
                messages.append(LLMMessage(role="user", content=message.text))

                # Build system prompt with learner profile
                learner_context = profile.to_context_block()
                system = TELEGRAM_TUTOR_SYSTEM_PROMPT.format(practice_focus=practice_focus)
                if learner_context:
                    system = f"{system}\n\n## About This Learner\n{learner_context}"

                chat_response = self.llm.chat_with_buttons(
                    messages=messages,
                    system=system,
                    max_tokens=300,
                )

                # Save both messages to database for shared memory
                self.db.save_message(user.id, "user", message.text, "telegram")
                self.db.save_message(user.id, "assistant", chat_response.text, "telegram")

                # Track message count and trigger extraction periodically
                self._message_count[user.id] = self._message_count.get(user.id, 0) + 1
                if self._message_count[user.id] >= EXTRACTION_INTERVAL:
                    self._message_count[user.id] = 0
                    # Get last few messages for extraction (don't block response)
                    recent = [{"role": m.role, "content": m.content} for m in history[-6:]]
                    recent.append({"role": "user", "content": message.text})
                    recent.append({"role": "assistant", "content": chat_response.text})
                    self.memory_extractor.schedule_extraction(user.id, recent, "telegram")

                # Build reply with optional AI-generated buttons
                if chat_response.buttons:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=btn.label,
                            callback_data=f"ai_{btn.value[:50]}",  # Prefix to distinguish from menu buttons
                        )]
                        for btn in chat_response.buttons[:4]  # Max 4 buttons
                    ])
                    await message.answer(chat_response.text, reply_markup=keyboard)
                else:
                    await message.answer(chat_response.text)

            except Exception as e:
                console.print(f"[red]Text handler error: {e}[/red]")
                await message.answer(self._format_error(e, "text"))

        @self.dp.message(F.voice)
        async def voice_handler(message: Message) -> None:
            """Handle incoming voice notes via OpenAI Realtime API."""
            user = self._ensure_user(message.from_user.id)
            if not user:
                await message.answer("Error: Could not find your user profile.")
                return

            console.print(f"[bold cyan]Voice note received[/bold cyan] from user {user.id}")

            # Download voice file
            voice = message.voice
            file = await self.bot.get_file(voice.file_id)
            voice_data = await self.bot.download_file(file.file_path)
            ogg_bytes = voice_data.read()

            console.print(f"[dim]Downloaded {len(ogg_bytes)} bytes, duration: {voice.duration}s[/dim]")

            # Save user's voice note audio to disk for future context
            voice_notes_dir = Path(self.config.database_path).parent / "voice_notes"
            voice_notes_dir.mkdir(parents=True, exist_ok=True)
            user_audio_path = voice_notes_dir / f"user_{user.id}_{message.message_id}.ogg"
            user_audio_path.write_bytes(ogg_bytes)

            # Load conversation history (shared across voice and telegram)
            # Pass full ConversationMessage objects so voice_handler can access audio_path
            history = self.db.get_conversation_history(user.id, limit=15)

            # Initialize voice client
            voice_client = RealtimeVoiceClient(
                api_key=self.config.openai_api_key,
                system_prompt=VOICE_NOTE_TUTOR_PROMPT,
            )

            # Process voice note
            try:
                response = await voice_client.process_voice_note(
                    ogg_bytes,
                    conversation_history=history,  # Pass ConversationMessage objects directly
                )

                # Save user transcript with audio path for future context
                if response.user_transcript:
                    self.db.save_message(
                        user.id,
                        "user",
                        response.user_transcript,
                        "telegram_voice",
                        audio_path=str(user_audio_path),
                    )
                # Save assistant transcript (no audio path - we could save it but text is sufficient)
                if response.assistant_transcript:
                    self.db.save_message(
                        user.id,
                        "assistant",
                        response.assistant_transcript,
                        "telegram_voice",
                    )

                # Send voice response
                if response.audio_bytes:
                    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                        f.write(response.audio_bytes)
                        temp_path = f.name

                    try:
                        voice_file = FSInputFile(temp_path)
                        await message.answer_voice(voice_file)
                    finally:
                        os.unlink(temp_path)
                else:
                    # Fallback to text if no audio
                    await message.answer(response.assistant_transcript or "I couldn't process that voice note.")

            except Exception as e:
                console.print(f"[red]Voice processing error: {e}[/red]")
                await message.answer(self._format_error(e, "voice"))

    def _ensure_user(self, telegram_id: int) -> User | None:
        """Get or create a user by Telegram ID."""
        user = self.db.get_user_by_telegram(telegram_id)
        if user:
            return user

        # Create new user
        new_user = User(
            phone_number=self.config.user_phone_number,
            telegram_id=telegram_id,
            timezone=self.config.timezone,
        )
        user_id = self.db.create_user(new_user)
        return self.db.get_user(user_id)

    def _format_error(self, error: Exception, channel: str) -> str:
        """Format error message for user with style and useful info."""
        err_str = str(error).lower()

        # Detect billing/credits issues
        if "credit balance" in err_str or "insufficient_quota" in err_str:
            if "anthropic" in err_str or channel == "text":
                return "🪫 *Claude's brain needs fuel*\n\n`ANTHROPIC_CREDITS_DEPLETED`\n\nThe text AI ran out of API credits. Voice notes still work tho 🎤"
            else:
                return "🪫 *OpenAI ran dry*\n\n`OPENAI_CREDITS_DEPLETED`\n\nVoice AI needs more credits. Try text instead 💬"

        if "rate_limit" in err_str or "rate limit" in err_str:
            return "⏱️ *Too fast, güey*\n\n`RATE_LIMITED`\n\nChill for a sec and try again"

        if "api_key" in err_str or "authentication" in err_str or "401" in err_str:
            return "🔐 *Auth glitch*\n\n`API_KEY_INVALID`\n\nSomething's wrong with the API keys"

        if "timeout" in err_str or "timed out" in err_str:
            return "⏳ *AI took too long*\n\n`TIMEOUT`\n\nTry again—sometimes the AI needs a moment"

        # Generic error with snippet
        error_snippet = str(error)[:100]
        if len(str(error)) > 100:
            error_snippet += "..."

        if channel == "voice":
            return f"🔧 *Voice glitch*\n\n`{error_snippet}`\n\nTry text instead?"
        else:
            return f"🔧 *Glitch in the matrix*\n\n`{error_snippet}`"

    async def send_vocabulary_reminder(self, items: list[CurriculumItem]) -> None:
        """Proactively send vocabulary to review."""
        if not items:
            return

        text = "🌅 *Time to practice!*\n\n"
        for item in items[:5]:
            text += f"• **{item.spanish}** = {item.english}\n"

        text += "\nReply with /review for more details!"

        await self.bot.send_message(
            chat_id=self.config.telegram_user_id,
            text=text,
            parse_mode="Markdown",
        )

    async def send_exercise(self, exercise: dict) -> None:
        """Send a practice exercise."""
        await self.bot.send_message(
            chat_id=self.config.telegram_user_id,
            text=exercise.get("prompt", "Practice time!"),
            parse_mode="Markdown",
        )

    async def send_message(self, text: str) -> None:
        """Send a message to the configured user."""
        await self.bot.send_message(
            chat_id=self.config.telegram_user_id,
            text=text,
            parse_mode="Markdown",
        )

    async def run(self) -> None:
        """Start the bot."""
        console.rule("[bold green]Starting Telegram Bot")
        await self.dp.start_polling(self.bot)
