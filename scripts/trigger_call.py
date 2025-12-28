#!/usr/bin/env python3
"""Manually trigger a voice call for testing."""

import asyncio

from rich.console import Console

from span.config import Config
from span.voice.dialout import trigger_voice_call


console = Console()


async def main() -> None:
    console.rule("[bold blue]Triggering Voice Call (Daily)")

    config = Config.from_env()

    console.print(f"Calling: {config.user_phone_number}")
    console.print(f"From: {config.daily_phone_number}")
    console.print()

    result = await trigger_voice_call(config)

    if "error" in result:
        console.print(f"[red]Failed: {result['error']}[/red]")
    else:
        console.print(f"[green]Call initiated![/green]")
        if result.get("room_url"):
            console.print(f"Room: {result.get('room_url')}")


if __name__ == "__main__":
    asyncio.run(main())
