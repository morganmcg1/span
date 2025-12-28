"""Main entry point for the voice server."""

import uvicorn
from rich.console import Console
from rich.panel import Panel

from span.config import Config

console = Console()


def main():
    """Run the voice server."""
    config = Config.from_env()

    console.print(
        Panel.fit(
            f"Host: {config.voice_server_host}\n"
            f"Port: {config.voice_server_port}\n"
            "\nFor local development with dial-in:\n"
            "  1. Run: ngrok http 7860\n"
            "  2. Configure your Daily phone number webhook to the ngrok URL",
            title="Starting Span Voice Server (Daily)",
        )
    )

    uvicorn.run(
        "span.voice.server:app",
        host=config.voice_server_host,
        port=config.voice_server_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
