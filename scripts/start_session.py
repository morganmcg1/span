#!/usr/bin/env python3
"""Start a voice session and send the room link via Telegram."""

import asyncio

import httpx
from aiogram import Bot
from rich.console import Console

from span.config import Config


console = Console()


async def main() -> None:
    console.rule("[bold blue]Starting Voice Session")

    config = Config.from_env()

    if not config.telegram_bot_token:
        console.print("[red]Error: TELEGRAM_BOT_TOKEN not set[/red]")
        return

    if not config.telegram_user_id:
        console.print("[red]Error: TELEGRAM_USER_ID not set[/red]")
        return

    # Hit the /web endpoint to create a room
    url = f"http://{config.voice_server_host}:{config.voice_server_port}/web"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            result = response.json()

            if "error" in result:
                console.print(f"[red]Failed: {result['error']}[/red]")
                return

            room_url = result.get("room_url")
            if not room_url:
                console.print("[red]No room URL returned[/red]")
                return

            console.print(f"[green]Room created: {room_url}[/green]")

            # Send via Telegram
            bot = Bot(token=config.telegram_bot_token)
            await bot.send_message(
                chat_id=config.telegram_user_id,
                text=f"🎙️ Voice session ready!\n\n{room_url}",
            )
            console.print("[green]Link sent to Telegram![/green]")

    except httpx.ConnectError:
        console.print("[red]Could not connect to voice server. Is it running?[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    asyncio.run(main())
