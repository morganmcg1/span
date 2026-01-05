"""OpenAI Realtime API client for Telegram voice notes."""

import asyncio
import base64
import io
import json
import random
from dataclasses import dataclass
from pathlib import Path

import websockets
from pydub import AudioSegment
from rich.console import Console

from span.db.models import ConversationMessage

console = Console()

# OpenAI Realtime API voices - randomized each session for variety
# Note: fable, onyx, nova are TTS-only and NOT supported by Realtime API
OPENAI_REALTIME_VOICES = [
    "alloy", "ash", "ballad", "coral", "echo",
    "sage", "shimmer", "verse", "marin", "cedar",
]


@dataclass
class VoiceResponse:
    """Response from voice processing."""

    audio_bytes: bytes  # OGG/Opus format for Telegram
    user_transcript: str
    assistant_transcript: str


class RealtimeVoiceClient:
    """Client for processing voice notes via OpenAI Realtime API."""

    WS_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime-2025-08-28"

    def __init__(self, api_key: str, system_prompt: str, voice: str | None = None):
        self.api_key = api_key
        self.system_prompt = system_prompt
        # Randomize voice each session for variety
        self.voice = voice or random.choice(OPENAI_REALTIME_VOICES)

    async def process_voice_note(
        self,
        ogg_audio: bytes,
        conversation_history: list[ConversationMessage] | None = None,
    ) -> VoiceResponse:
        """Process a voice note and return audio response.

        Args:
            ogg_audio: Voice note audio in OGG/Opus format
            conversation_history: Recent messages as ConversationMessage objects.
                Messages with audio_path will be injected as audio, others as text.

        Returns:
            VoiceResponse with audio bytes (OGG), user transcript, and assistant transcript
        """
        # Convert OGG to PCM 24kHz
        pcm_audio = self._ogg_to_pcm(ogg_audio)
        pcm_b64 = base64.b64encode(pcm_audio).decode()

        console.print(f"[dim]Audio converted: {len(ogg_audio)} bytes OGG → {len(pcm_audio)} bytes PCM[/dim]")

        # Connect and process
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        async with websockets.connect(self.WS_URL, additional_headers=headers) as ws:
            # Configure session
            await self._configure_session(ws)

            # Inject conversation history
            if conversation_history:
                await self._inject_conversation_history(ws, conversation_history)

            # Send audio and get response
            await self._send_audio(ws, pcm_b64)
            try:
                async with asyncio.timeout(90):
                    user_transcript, assistant_transcript, response_audio = await self._receive_response(ws)
            except asyncio.TimeoutError as e:
                raise RuntimeError("Timeout waiting for Realtime API response") from e

        # Convert response to OGG
        if response_audio:
            ogg_response = self._pcm_to_ogg(response_audio)
            console.print(f"[dim]Response converted: {len(response_audio)} bytes PCM → {len(ogg_response)} bytes OGG[/dim]")
        else:
            ogg_response = b""

        return VoiceResponse(
            audio_bytes=ogg_response,
            user_transcript=user_transcript,
            assistant_transcript=assistant_transcript,
        )

    async def _configure_session(self, ws) -> None:
        """Send session.update to configure the session."""
        session_config = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": self.system_prompt,
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": None,  # Disable VAD for single-turn
            },
        }
        await ws.send(json.dumps(session_config))
        await self._wait_for_event(ws, "session.updated")
        console.print("[dim]Session configured[/dim]")

    async def _inject_conversation_history(self, ws, history: list[ConversationMessage]) -> None:
        """Inject recent conversation history as mixed audio/text items.

        User voice messages (with audio_path) are injected as audio for pronunciation context.
        Text messages and assistant responses are injected as text.
        """
        audio_count = 0
        text_count = 0

        for msg in history:
            if not msg.content:
                continue

            # Check if this is a user voice message with audio file
            if msg.role == "user" and msg.audio_path and Path(msg.audio_path).exists():
                # Inject as audio for pronunciation context
                try:
                    audio_bytes = Path(msg.audio_path).read_bytes()
                    pcm_audio = self._ogg_to_pcm(audio_bytes)
                    pcm_b64 = base64.b64encode(pcm_audio).decode()

                    item_create = {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_audio", "audio": pcm_b64}],
                        },
                    }
                    await ws.send(json.dumps(item_create))
                    await self._wait_for_event(ws, "conversation.item.created")
                    audio_count += 1
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not load audio {msg.audio_path}: {e}[/yellow]")
                    # Fall back to text transcript
                    await self._inject_text_message(ws, msg.role, msg.content)
                    text_count += 1
            else:
                # Inject as text (text messages or assistant responses)
                await self._inject_text_message(ws, msg.role, msg.content)
                text_count += 1

        console.print(f"[dim]Injected history: {audio_count} audio + {text_count} text messages[/dim]")

    async def _inject_text_message(self, ws, role: str, content: str) -> None:
        """Inject a single text message into the conversation."""
        # Map to Realtime API content format
        if role == "user":
            content_item = [{"type": "input_text", "text": content}]
        else:
            content_item = [{"type": "text", "text": content}]

        item_create = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": role,
                "content": content_item,
            },
        }
        await ws.send(json.dumps(item_create))
        await self._wait_for_event(ws, "conversation.item.created")

    async def _send_audio(self, ws, pcm_b64: str) -> None:
        """Send audio buffer and commit."""
        # Chunk large audio (Realtime API has limits per event)
        chunk_size = 15 * 1024 * 1024  # 15MB per chunk (under 16MB limit)
        for i in range(0, len(pcm_b64), chunk_size):
            chunk = pcm_b64[i : i + chunk_size]
            await ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": chunk,
                    }
                )
            )

        # Commit the buffer
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await self._wait_for_event(ws, "input_audio_buffer.committed")

        # Request response
        await ws.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                    },
                }
            )
        )
        console.print("[dim]Audio sent, waiting for response...[/dim]")

    async def _receive_response(self, ws) -> tuple[str, str, bytes]:
        """Receive and accumulate response audio and transcripts."""
        user_transcript = ""
        assistant_transcript = ""
        audio_chunks: list[bytes] = []

        async for message in ws:
            event = json.loads(message)
            event_type = event.get("type")

            if event_type == "conversation.item.input_audio_transcription.completed":
                user_transcript = event.get("transcript", "")
                console.print(f"[cyan]User said:[/cyan] {user_transcript[:100]}...")

            elif event_type == "response.audio_transcript.delta":
                assistant_transcript += event.get("delta", "")

            elif event_type == "response.audio.delta":
                audio_b64 = event.get("delta", "")
                if audio_b64:
                    audio_chunks.append(base64.b64decode(audio_b64))

            elif event_type == "response.done":
                console.print(f"[green]Assistant:[/green] {assistant_transcript[:100]}...")
                break

            elif event_type == "error":
                error = event.get("error", {})
                raise RuntimeError(f"Realtime API error: {error.get('message', event)}")

        response_audio = b"".join(audio_chunks)
        return user_transcript, assistant_transcript, response_audio

    async def _wait_for_event(self, ws, expected_type: str, timeout: float = 30.0) -> dict:
        """Wait for a specific event type."""
        try:
            async with asyncio.timeout(timeout):
                async for message in ws:
                    event = json.loads(message)
                    if event.get("type") == expected_type:
                        return event
                    if event.get("type") == "error":
                        error = event.get("error", {})
                        raise RuntimeError(f"Realtime API error: {error.get('message', event)}")
        except asyncio.TimeoutError:
            raise RuntimeError(f"Timeout waiting for {expected_type}")
        return {}

    def _ogg_to_pcm(self, ogg_bytes: bytes) -> bytes:
        """Convert OGG/Opus to PCM 24kHz 16-bit mono."""
        audio = AudioSegment.from_ogg(io.BytesIO(ogg_bytes))
        audio = audio.set_frame_rate(24000).set_channels(1).set_sample_width(2)
        return audio.raw_data

    def _pcm_to_ogg(self, pcm_bytes: bytes) -> bytes:
        """Convert PCM 24kHz 16-bit mono to OGG/Opus."""
        audio = AudioSegment(
            data=pcm_bytes,
            sample_width=2,  # 16-bit
            frame_rate=24000,
            channels=1,
        )
        buffer = io.BytesIO()
        audio.export(buffer, format="ogg", codec="libopus")
        buffer.seek(0)
        return buffer.read()
