"""Main entry point for the Telegram bot."""

import asyncio

from rich.console import Console
from rich.panel import Panel

from span.config import Config
from span.db.database import Database
from span.telegram.bot import SpanTelegramBot


console = Console()


async def main():
    """Run the Telegram bot."""
    config = Config.from_env()
    config.ensure_database_dir()

    db = Database(config.database_path)
    db.init_schema()

    console.print(
        Panel.fit(
            f"Bot token: {config.telegram_bot_token[:10]}...\n"
            f"User ID: {config.telegram_user_id}\n"
            f"Voice server: http://localhost:{config.voice_server_port}",
            title="Starting Span Telegram Bot",
        )
    )

    bot = SpanTelegramBot(config, db)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
