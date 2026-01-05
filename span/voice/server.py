"""FastAPI server for Daily PSTN voice calls."""

import asyncio
import aiohttp
import time
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.transports.daily.transport import DailyDialinSettings
from rich.console import Console

from span.config import Config
from span.curriculum.scheduler import CurriculumScheduler
from span.db.database import Database
from span.voice.bot import SpanishTutorBot


console = Console()

# Global state
config: Config | None = None
db: Database | None = None

# Default user ID used when no user is found in database
DEFAULT_USER_ID = 1

# Persistent room name - reused to avoid iOS permission prompts on each new URL
PERSISTENT_ROOM_NAME = "span-voice-room"

# Track active bot tasks per room to prevent duplicates
_active_bot_tasks: dict[str, asyncio.Task] = {}

# Landing page HTML for iOS mic permission handling
LANDING_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Span Voice Call</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            padding: 40px 20px;
            text-align: center;
            background: #F2F2F7;
            min-height: 100vh;
            margin: 0;
            box-sizing: border-box;
        }
        .container {
            max-width: 400px;
            margin: 0 auto;
            background: white;
            padding: 32px 24px;
            border-radius: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        h1 { margin: 0 0 8px 0; font-size: 28px; }
        .subtitle { color: #666; margin-bottom: 32px; }
        .btn {
            background: #007AFF;
            color: white;
            padding: 16px 32px;
            border: none;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: background 0.2s;
        }
        .btn:active { background: #0056CC; }
        .btn:disabled { background: #999; }
        .error { color: #FF3B30; margin-top: 20px; }
        .success { color: #34C759; margin-top: 20px; }
        .instructions {
            margin-top: 20px;
            text-align: left;
            padding: 16px;
            background: #FFF3CD;
            border-radius: 12px;
            font-size: 14px;
        }
        .instructions ol { margin: 8px 0 0 0; padding-left: 20px; }
        .instructions li { margin: 8px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Voice Practice</h1>
        <p class="subtitle">Tap below to start your Spanish session</p>
        <button class="btn" id="startBtn" onclick="startCall()">Start Voice Call</button>
        <div id="status"></div>
    </div>
    <script>
        const roomUrl = new URLSearchParams(location.search).get('room');

        async function startCall() {
            const status = document.getElementById('status');
            const btn = document.getElementById('startBtn');

            btn.disabled = true;
            btn.textContent = 'Requesting microphone...';

            try {
                const stream = await navigator.mediaDevices.getUserMedia({audio: true});
                // Stop the stream immediately - we just needed permission
                stream.getTracks().forEach(track => track.stop());

                status.innerHTML = '<p class="success">Microphone enabled! Joining call...</p>';
                window.location.href = roomUrl;
            } catch (err) {
                btn.disabled = false;
                btn.textContent = 'Try Again';

                let errorMsg = 'Microphone access denied';
                if (err.name === 'NotAllowedError') {
                    errorMsg = 'Microphone permission denied';
                } else if (err.name === 'NotFoundError') {
                    errorMsg = 'No microphone found';
                }

                status.innerHTML = `
                    <p class="error">${errorMsg}</p>
                    <div class="instructions">
                        <strong>To fix on iOS:</strong>
                        <ol>
                            <li>Open <strong>Settings</strong></li>
                            <li>Go to <strong>Privacy & Security > Microphone</strong></li>
                            <li>Enable microphone for your browser app</li>
                            <li>Return here and tap "Try Again"</li>
                        </ol>
                    </div>`;
            }
        }
    </script>
</body>
</html>
"""


def _get_user_and_lesson_plan(db: Database) -> tuple[int, object | None]:
    """Get user ID and lesson plan, falling back to default user if needed.

    Returns:
        Tuple of (user_id, lesson_plan)
    """
    scheduler = CurriculumScheduler(db)
    user = db.get_user(DEFAULT_USER_ID)

    if user:
        return user.id, scheduler.create_daily_plan(user.id)

    # Fallback to default user ID
    console.print(
        f"[yellow]Warning: No user found in database, using default user_id={DEFAULT_USER_ID}. "
        f"Create a user first via Telegram /start command.[/yellow]"
    )
    return DEFAULT_USER_ID, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    global config, db
    config = Config.from_env()
    db = Database(config.database_path)
    db.init_schema()
    console.print("[green]Voice server initialized[/green]")
    yield
    console.print("[yellow]Voice server shutting down[/yellow]")


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/daily-dialin-webhook")
async def daily_dialin_webhook(request: Request):
    """
    Handle incoming Daily PSTN dial-in calls.
    Daily calls this webhook when someone calls your phone number.
    """
    data = await request.json()
    console.print(f"[blue]Incoming call: {data}[/blue]")

    # Extract dial-in settings
    dialin_settings = data.get("dialin_settings", {})

    # Get user and lesson plan
    user_id, lesson_plan = _get_user_and_lesson_plan(db)

    # Create bot with database for tool calling
    bot = SpanishTutorBot(config, lesson_plan, db=db, user_id=user_id)

    # For dial-in, Daily provides room_url and token
    room_url = data.get("room_url")
    token = data.get("token")

    if room_url and token:
        # Create transport with dial-in settings
        transport = bot.create_transport(room_url, token)

        # Set dial-in settings
        if dialin_settings:
            transport.params.dialin_settings = DailyDialinSettings(
                call_id=dialin_settings.get("call_id"),
                call_domain=dialin_settings.get("call_domain"),
            )

        # Create and run pipeline
        pipeline = await bot.create_pipeline(transport)
        task = PipelineTask(pipeline, params=bot.get_pipeline_params())
        runner = PipelineRunner()

        try:
            console.print("[green]Starting voice conversation[/green]")
            await runner.run(task)
        except Exception as e:
            console.print(f"[red]Pipeline error: {e}[/red]")
        finally:
            console.print("[blue]Voice conversation ended[/blue]")

    return {"status": "ok"}


@app.api_route("/dialout", methods=["GET", "POST"])
async def trigger_dialout():
    """API endpoint to initiate an outbound call."""
    if not config.daily_api_key:
        return {"error": "DAILY_API_KEY not configured"}

    if not config.user_phone_number:
        return {"error": "USER_PHONE_NUMBER not configured"}

    try:
        # Create a Daily room for the call
        async with aiohttp.ClientSession() as session:
            # Create room
            async with session.post(
                "https://api.daily.co/v1/rooms",
                headers={
                    "Authorization": f"Bearer {config.daily_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "properties": {
                        "enable_dialout": True,
                        "exp": int(time.time()) + 3600,  # Room expires in 1 hour
                    }
                },
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return {"error": f"Failed to create room: {error}"}
                room_data = await resp.json()
                room_url = room_data["url"]
                room_name = room_data["name"]

            # Get meeting token
            async with session.post(
                "https://api.daily.co/v1/meeting-tokens",
                headers={
                    "Authorization": f"Bearer {config.daily_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "properties": {
                        "room_name": room_name,
                        "is_owner": True,
                    }
                },
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return {"error": f"Failed to create token: {error}"}
                token_data = await resp.json()
                token = token_data["token"]

        # Get user and lesson plan
        user_id, lesson_plan = _get_user_and_lesson_plan(db)

        # Create bot and transport with database for tool calling
        bot = SpanishTutorBot(config, lesson_plan, db=db, user_id=user_id)
        transport = bot.create_transport(room_url, token)

        # Start dial-out in background
        import asyncio

        async def run_dialout():
            try:
                # Set up dial-out when we join the room
                @transport.event_handler("on_call_state_updated")
                async def on_call_state_updated(transport, state):
                    if state == "joined":
                        console.print("[blue]Joined room, starting dial-out...[/blue]")
                        await transport.start_dialout(
                            settings={
                                "phoneNumber": config.user_phone_number,
                                "callerId": config.daily_phone_number,
                            }
                        )

                @transport.event_handler("on_dialout_answered")
                async def on_dialout_answered(transport, data):
                    console.print("[green]Call answered![/green]")

                # Create and run pipeline (this handles joining the room)
                pipeline = await bot.create_pipeline(transport)
                task = PipelineTask(pipeline, params=bot.get_pipeline_params())
                runner = PipelineRunner()

                console.print("[green]Starting outbound call[/green]")
                await runner.run(task)
            except Exception as e:
                console.print(f"[red]Dial-out error: {e}[/red]")
            finally:
                console.print("[blue]Call ended[/blue]")

        # Run in background
        asyncio.create_task(run_dialout())

        console.print(f"[green]Initiated call to {config.user_phone_number}[/green]")
        return {"status": "initiated", "room_url": room_url}

    except Exception as e:
        console.print(f"[red]Failed to initiate call: {e}[/red]")
        return {"error": str(e)}


async def _get_or_create_persistent_room(session: aiohttp.ClientSession) -> tuple[str, str]:
    """Get existing persistent room or create it if it doesn't exist.

    Returns (room_url, room_name).
    """
    headers = {
        "Authorization": f"Bearer {config.daily_api_key}",
        "Content-Type": "application/json",
    }

    # Try to get existing room
    async with session.get(
        f"https://api.daily.co/v1/rooms/{PERSISTENT_ROOM_NAME}",
        headers=headers,
    ) as resp:
        if resp.status == 200:
            room_data = await resp.json()
            return room_data["url"], room_data["name"]

    # Room doesn't exist, create it (no exp = never expires)
    async with session.post(
        "https://api.daily.co/v1/rooms",
        headers=headers,
        json={
            "name": PERSISTENT_ROOM_NAME,
            "properties": {
                "enable_prejoin_ui": False,
            }
        },
    ) as resp:
        if resp.status != 200:
            error = await resp.text()
            raise Exception(f"Failed to create room: {error}")
        room_data = await resp.json()
        return room_data["url"], room_data["name"]


def _build_start_url(room_url: str) -> str | None:
    """Build the voice-start landing page URL if public URL is configured."""
    if not config.voice_server_public_url:
        return None
    return f"{config.voice_server_public_url}/voice-start?{urlencode({'room': room_url})}"


@app.get("/voice-start")
async def voice_start_page(room: str):
    """Landing page that requests mic permission before redirecting to Daily room.

    This helps iOS devices that have cached a "denied" permission state.
    The page explicitly calls getUserMedia() which gives iOS a fresh chance
    to show the permission modal.
    """
    return HTMLResponse(content=LANDING_PAGE_HTML)


@app.api_route("/web", methods=["GET", "POST"])
async def start_web_session():
    """Start a browser-based voice session.

    Returns room URL - open it in your browser to talk to the bot.
    Uses a persistent room to avoid iOS permission prompts on each new URL.
    """
    global _active_bot_tasks

    if not config.daily_api_key:
        return {"error": "DAILY_API_KEY not configured"}

    try:
        async with aiohttp.ClientSession() as session:
            # Get or create persistent room
            room_url, room_name = await _get_or_create_persistent_room(session)

            # Check if there's already an active bot task for this room
            existing_task = _active_bot_tasks.get(room_name)
            if existing_task is not None and not existing_task.done():
                console.print(f"[yellow]Bot already active for room {room_name}, returning existing URL[/yellow]")
                response = {
                    "status": "ready",
                    "room_url": room_url,
                    "instructions": "Open the room URL in your browser to start talking",
                    "note": "Bot already active in room",
                }
                start_url = _build_start_url(room_url)
                if start_url:
                    response["start_url"] = start_url
                return response

            # Get meeting token for bot
            async with session.post(
                "https://api.daily.co/v1/meeting-tokens",
                headers={
                    "Authorization": f"Bearer {config.daily_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "properties": {
                        "room_name": room_name,
                        "is_owner": True,
                    }
                },
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return {"error": f"Failed to create token: {error}"}
                token_data = await resp.json()
                token = token_data["token"]

        # Get user and lesson plan
        user_id, lesson_plan = _get_user_and_lesson_plan(db)

        # Create bot
        bot = SpanishTutorBot(config, lesson_plan, db=db, user_id=user_id)
        transport = bot.create_transport(room_url, token)

        # Run bot in background
        async def run_bot():
            try:
                pipeline = await bot.create_pipeline(transport)
                task = PipelineTask(pipeline, params=bot.get_pipeline_params())
                runner = PipelineRunner()
                console.print("[green]Bot joined room, waiting for user...[/green]")
                await runner.run(task)
            except Exception as e:
                console.print(f"[red]Bot error: {e}[/red]")
            finally:
                console.print("[blue]Session ended[/blue]")
                # Clean up task reference when done
                _active_bot_tasks.pop(room_name, None)

        # Create and track the bot task
        bot_task = asyncio.create_task(run_bot())
        _active_bot_tasks[room_name] = bot_task

        console.print(f"[green]Room created: {room_url}[/green]")
        response = {
            "status": "ready",
            "room_url": room_url,
            "instructions": "Open the room URL in your browser to start talking",
        }
        start_url = _build_start_url(room_url)
        if start_url:
            response["start_url"] = start_url
        return response

    except Exception as e:
        console.print(f"[red]Failed to start session: {e}[/red]")
        return {"error": str(e)}


def create_app() -> FastAPI:
    """Create the FastAPI app."""
    return app
