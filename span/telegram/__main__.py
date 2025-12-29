"""Main entry point for the Telegram bot."""

import asyncio

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from rich.console import Console
from rich.panel import Panel

from span.config import Config
from span.db.database import Database
from span.telegram.bot import SpanTelegramBot


console = Console()


async def send_daily_voice_reminder(bot: SpanTelegramBot, config: Config) -> None:
    """Send daily voice chat reminder at 9:55am."""
    voice_server_url = f"http://localhost:{config.voice_server_port}/web"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(voice_server_url) as resp:
                if resp.status != 200:
                    console.print("[yellow]Voice server not available for daily reminder[/yellow]")
                    # Send reminder anyway without room link
                    await bot.send_message(
                        "🌅 *¡Buenos días!* Time for your daily Spanish practice!\n\n"
                        "Start the voice server and use /v to begin a voice chat."
                    )
                    return

                data = await resp.json()
                room_url = data.get("room_url")

                if room_url:
                    await bot.send_message(
                        "🌅 *¡Buenos días!* Time for your daily Spanish practice!\n\n"
                        f"🎤 Voice room ready:\n{room_url}\n\n"
                        "Open the link, allow mic access, and let's practice!"
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


async def main():
    """Run the Telegram bot."""
    config = Config.from_env()
    config.ensure_database_dir()

    db = Database(config.database_path)
    db.init_schema()

    bot = SpanTelegramBot(config, db)

    # Set up daily 9:55am reminder scheduler
    scheduler = AsyncIOScheduler(timezone=config.timezone)
    scheduler.add_job(
        send_daily_voice_reminder,
        CronTrigger(hour=9, minute=55),
        args=[bot, config],
        id="daily_voice_reminder",
        name="Daily 9:55am voice chat reminder",
    )
    scheduler.start()

    console.print(
        Panel.fit(
            f"Bot token: {config.telegram_bot_token[:10]}...\n"
            f"User ID: {config.telegram_user_id}\n"
            f"Voice server: http://localhost:{config.voice_server_port}\n"
            f"Daily reminder: 9:55am ({config.timezone})",
            title="Starting Span Telegram Bot",
        )
    )

    try:
        await bot.run()
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
