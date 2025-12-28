#!/usr/bin/env python3
"""Run the voice server for Daily PSTN connections."""

import uvicorn
from rich.console import Console

from span.config import Config


console = Console()


def main() -> None:
    console.rule("[bold blue]Starting Span Voice Server (Daily)")

    config = Config.from_env()

    console.print(f"Host: {config.voice_server_host}")
    console.print(f"Port: {config.voice_server_port}")
    console.print()

    if not config.daily_api_key:
        console.print("[yellow]Warning: DAILY_API_KEY not set.[/yellow]")
        console.print("Get your API key at: https://pipecat.daily.co")
        console.print()

    console.print("For local development with dial-in:")
    console.print("  1. Run: ngrok http 7860")
    console.print("  2. Configure your Daily phone number webhook to the ngrok URL")
    console.print()

    uvicorn.run(
        "span.voice.server:app",
        host=config.voice_server_host,
        port=config.voice_server_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
