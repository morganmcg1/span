"""Main entry point for the Telegram bot."""

import asyncio
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from pytz import timezone as pytz_timezone
from rich.console import Console
from rich.panel import Panel

from span.config import Config
from span.db.database import Database
from span.telegram.bot import SpanTelegramBot


console = Console()

# Daily reminder window (Dublin time)
REMINDER_HOUR_START = 9
REMINDER_MINUTE_START = 30
REMINDER_HOUR_END = 10
REMINDER_MINUTE_END = 30


def get_random_reminder_time(tz_name: str) -> datetime:
    """Get a random time between 9:30-10:30am for tomorrow (or today if before window)."""
    tz = pytz_timezone(tz_name)
    now = datetime.now(tz)

    # Random minute offset from 9:30 (0-60 minutes = 9:30-10:30)
    random_minutes = random.randint(0, 60)
    reminder_hour = REMINDER_HOUR_START
    reminder_minute = REMINDER_MINUTE_START + random_minutes
    if reminder_minute >= 60:
        reminder_hour += 1
        reminder_minute -= 60

    # Start with today
    reminder_time = now.replace(hour=reminder_hour, minute=reminder_minute, second=0, microsecond=0)

    # If we're past today's window, schedule for tomorrow
    if now >= reminder_time:
        reminder_time += timedelta(days=1)

    return reminder_time


def schedule_next_reminder(
    scheduler: AsyncIOScheduler,
    bot: SpanTelegramBot,
    config: Config,
) -> datetime:
    """Schedule the next daily reminder at a random time."""
    next_time = get_random_reminder_time(config.timezone)

    # Remove existing job if any
    if scheduler.get_job("daily_voice_reminder"):
        scheduler.remove_job("daily_voice_reminder")

    scheduler.add_job(
        send_daily_voice_reminder,
        DateTrigger(run_date=next_time),
        args=[scheduler, bot, config],
        id="daily_voice_reminder",
        name=f"Daily voice reminder at {next_time.strftime('%H:%M')}",
    )

    return next_time


async def send_daily_voice_reminder(
    scheduler: AsyncIOScheduler,
    bot: SpanTelegramBot,
    config: Config,
) -> None:
    """Send daily voice chat reminder and schedule the next one."""
    voice_server_url = f"http://localhost:{config.voice_server_port}/web"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(voice_server_url) as resp:
                if resp.status != 200:
                    console.print("[yellow]Voice server not available for daily reminder[/yellow]")
                    await bot.send_message(
                        "🌅 *¡Buenos días!* Time for your daily Spanish practice!\n\n"
                        "Start the voice server and use /v to begin a voice chat."
                    )
                else:
                    data = await resp.json()
                    room_url = data.get("room_url")
                    # Prefer start_url (landing page for iOS mic permissions)
                    voice_url = data.get("start_url") or room_url

                    if voice_url:
                        await bot.send_message(
                            "🌅 *¡Buenos días!* Time for your daily Spanish practice!\n\n"
                            f"🎤 Voice room ready:\n{voice_url}\n\n"
                            "Tap the link and press 'Start Voice Call'!"
                        )
                        console.print(f"[green]Sent daily voice reminder with room: {room_url}[/green]")
                    else:
                        await bot.send_message(
                            "🌅 *¡Buenos días!* Time for your daily Spanish practice!\n\n"
                            "Use /v to start a voice chat!"
                        )

    except aiohttp.ClientConnectorError:
        console.print("[yellow]Could not connect to voice server for daily reminder[/yellow]")
        await bot.send_message(
            "🌅 *¡Buenos días!* Time for your daily Spanish practice!\n\n"
            "Start the voice server and use /v to begin!"
        )
    except Exception as e:
        console.print(f"[red]Daily reminder error: {e}[/red]")

    # Schedule next reminder for tomorrow at a new random time
    next_time = schedule_next_reminder(scheduler, bot, config)
    console.print(f"[blue]Next reminder scheduled for {next_time.strftime('%Y-%m-%d %H:%M')}[/blue]")


async def main():
    """Run the Telegram bot."""
    config = Config.from_env()
    config.ensure_database_dir()

    db = Database(config.database_path)
    db.init_schema()

    bot = SpanTelegramBot(config, db)

    # Set up daily reminder scheduler with random time between 9:30-10:30am
    scheduler = AsyncIOScheduler(timezone=config.timezone)
    scheduler.start()

    next_reminder = schedule_next_reminder(scheduler, bot, config)

    console.print(
        Panel.fit(
            f"Bot token: {config.telegram_bot_token[:10]}...\n"
            f"User ID: {config.telegram_user_id}\n"
            f"Voice server: http://localhost:{config.voice_server_port}\n"
            f"Next reminder: {next_reminder.strftime('%Y-%m-%d %H:%M')} ({config.timezone})",
            title="Starting Span Telegram Bot",
        )
    )

    # Check for pending restart notification (from Claude Code push & restart)
    restart_file = Path(config.database_path).parent / "restart_pending.json"
    if restart_file.exists():
        try:
            restart_info = json.loads(restart_file.read_text())
            chat_id = restart_info.get("chat_id")
            summary = restart_info.get("summary", "")

            if chat_id:
                notification = "✅ *Bot restarted successfully.*\n\nNew code is now active."
                if summary:
                    notification += f"\n\n*Changes applied:*\n{summary}"

                await bot.bot.send_message(
                    chat_id=chat_id,
                    text=notification,
                    parse_mode="Markdown",
                )
                console.print("[green]Sent restart notification[/green]")

        except Exception as e:
            console.print(f"[yellow]Failed to send restart notification: {e}[/yellow]")
        finally:
            restart_file.unlink(missing_ok=True)

    try:
        await bot.run()
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
