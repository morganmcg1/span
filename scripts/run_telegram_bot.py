#!/usr/bin/env python3
"""Run the Telegram bot standalone."""

import asyncio

from rich.console import Console

from span.config import Config
from span.db.database import Database
from span.telegram.bot import SpanTelegramBot


console = Console()


async def main() -> None:
    console.rule("[bold blue]Starting Span Telegram Bot")

    config = Config.from_env()

    if not config.telegram_bot_token:
        console.print("[red]Error: TELEGRAM_BOT_TOKEN not set[/red]")
        return

    db = Database(config.database_path)
    db.init_schema()

    bot = SpanTelegramBot(config, db)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
