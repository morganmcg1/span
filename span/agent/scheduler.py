"""Agent scheduler for orchestrating daily lessons."""

import asyncio
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from rich.console import Console

from span.config import Config
from span.curriculum.scheduler import CurriculumScheduler
from span.db.database import Database
from span.telegram.bot import SpanTelegramBot
from span.voice.dialout import trigger_voice_call


console = Console()


class LessonAgent:
    """Orchestrates daily Spanish lessons via voice and Telegram."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self.telegram_bot = SpanTelegramBot(config, db)
        self.curriculum = CurriculumScheduler(db)

    def setup_schedule(self) -> None:
        """Configure the daily lesson schedule."""
        # Voice call at 9:50 AM
        self.scheduler.add_job(
            self.trigger_voice_lesson,
            CronTrigger(hour=9, minute=50),
            id="morning_call",
            name="Morning voice lesson",
        )

        # Telegram exercise at 2:30 PM
        self.scheduler.add_job(
            self.send_telegram_exercises,
            CronTrigger(hour=14, minute=30),
            id="afternoon_exercises",
            name="Afternoon Telegram exercises",
        )

        console.print("[green]Schedule configured:[/green]")
        console.print("  • 9:50 AM - Voice call")
        console.print("  • 2:30 PM - Telegram exercises")

    async def send_telegram_exercises(self) -> None:
        """Send vocabulary and exercises via Telegram."""
        console.rule("[yellow]Sending Telegram exercises")

        try:
            # Get user (single user mode)
            user = self.db.get_user(1)
            if not user:
                console.print("[red]No user found[/red]")
                return

            plan = self.curriculum.create_daily_plan(user.id)

            # Send vocabulary reminder
            all_items = plan.review_items[:3] + plan.new_items[:2]
            if all_items:
                await self.telegram_bot.send_vocabulary_reminder(all_items)

            # Send an exercise
            if plan.telegram_exercises:
                await asyncio.sleep(2)  # Brief pause
                await self.telegram_bot.send_exercise(plan.telegram_exercises[0])

            console.print("[green]Telegram exercises sent[/green]")
        except Exception as e:
            console.print(f"[red]Error sending Telegram exercises: {e}[/red]")

    async def trigger_voice_lesson(self) -> None:
        """Initiate the voice call lesson."""
        console.rule("[yellow]Triggering voice lesson")

        try:
            result = await trigger_voice_call(self.config)
            if "error" in result:
                console.print(f"[red]Voice call failed: {result['error']}[/red]")
                # Fallback: send Telegram notification
                await self.telegram_bot.send_message(
                    "📞 Couldn't reach you by phone. Use /practice to chat here instead!"
                )
            else:
                console.print(f"[green]Voice call initiated: {result.get('call_sid')}[/green]")
        except Exception as e:
            console.print(f"[red]Error triggering voice lesson: {e}[/red]")

    async def run_telegram_only(self) -> None:
        """Run only the Telegram bot (no scheduled jobs)."""
        console.rule("[bold green]Starting Telegram Bot Only")
        await self.telegram_bot.run()

    async def run(self) -> None:
        """Start the agent with scheduled jobs and Telegram bot."""
        console.rule("[bold green]Starting Lesson Agent")

        # Set up scheduled jobs
        self.setup_schedule()
        self.scheduler.start()

        console.print("[green]Scheduler started[/green]")
        console.print("Press Ctrl+C to stop\n")

        # Run Telegram bot (this blocks)
        try:
            await self.telegram_bot.run()
        except asyncio.CancelledError:
            console.print("[yellow]Agent shutting down[/yellow]")
        finally:
            self.scheduler.shutdown()


async def run_agent(config: Config | None = None) -> None:
    """Entry point for running the agent."""
    if config is None:
        config = Config.from_env()

    db = Database(config.database_path)
    db.init_schema()

    agent = LessonAgent(config, db)
    await agent.run()
