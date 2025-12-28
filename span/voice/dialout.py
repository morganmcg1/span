"""Outbound call functionality using Daily."""

import httpx
from rich.console import Console

from span.config import Config


console = Console()


async def trigger_voice_call(config: Config) -> dict:
    """
    Trigger an outbound voice call via the voice server.

    Returns:
        dict with status on success, or error message on failure.
    """
    url = f"http://{config.voice_server_host}:{config.voice_server_port}/dialout"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, timeout=30.0)
            result = response.json()

            if "error" in result:
                console.print(f"[red]Call failed: {result['error']}[/red]")
            else:
                console.print(f"[green]Call initiated[/green]")

            return result
    except httpx.ConnectError:
        error = "Could not connect to voice server. Is it running?"
        console.print(f"[red]{error}[/red]")
        return {"error": error}
    except Exception as e:
        console.print(f"[red]Error triggering call: {e}[/red]")
        return {"error": str(e)}


def trigger_voice_call_sync(config: Config) -> dict:
    """Synchronous wrapper for trigger_voice_call."""
    import asyncio
    return asyncio.run(trigger_voice_call(config))
