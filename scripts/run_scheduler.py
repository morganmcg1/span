#!/usr/bin/env python3
"""Run the full agent with scheduler and Telegram bot."""

import asyncio

from rich.console import Console

from span.agent.scheduler import run_agent
from span.config import Config


console = Console()


async def main() -> None:
    console.rule("[bold blue]Starting Span Lesson Agent")

    config = Config.from_env()

    console.print("Schedule:")
    console.print("  • 9:50 AM - Voice call")
    console.print("  • 2:30 PM - Telegram exercises")
    console.print()

    await run_agent(config)


if __name__ == "__main__":
    asyncio.run(main())
