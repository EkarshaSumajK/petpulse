"""Ports `Transcribe Audio` — Whisper (whisper-1) for voice-note messages
(spec §2)."""

from openai import AsyncOpenAI

from app.integrations.openai_client import transcribe_audio


async def analyze_voice_note(client: AsyncOpenAI, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    return await transcribe_audio(client, audio_bytes, filename)
