"""Ports `Transcribe Audio` (spec §2), upgraded from plain Whisper
transcription to gpt-audio — a voice note isn't always speech; a customer
may record the actual sound of their pet coughing/wheezing with little or
no talking, which pure speech-to-text would silently drop. Mirrors the
video audio-track pipeline (video.py) for the same reason."""

import base64

from openai import AsyncOpenAI

from app.config import Settings
from app.integrations.media_processing import convert_audio_to_mp3
from app.integrations.openai_client import analyze_audio

VOICE_NOTE_SYSTEM_PROMPT = (
    "You are listening to a WhatsApp voice note a pet owner sent to a veterinary assistant. Transcribe "
    "any speech. Also describe any non-speech sounds relevant to the pet's health (wheezing, coughing, "
    "labored breathing, whimpering) if the pet itself is audible — but be neutral and descriptive, not "
    "alarmist: describe what you hear, don't diagnose a condition from it. If the audio is faint or "
    "ambiguous, say so rather than over-interpreting it. You may be given background on the pet's known "
    "chronic conditions — use that only to describe what you hear more precisely, never to assert a "
    "diagnosis or claim a sound is present that you can't actually hear."
)


async def analyze_voice_note(
    client: AsyncOpenAI, settings: Settings, audio_bytes: bytes, pet_context: str = ""
) -> str:
    mp3_bytes = await convert_audio_to_mp3(audio_bytes)
    audio_b64 = base64.b64encode(mp3_bytes).decode()
    return await analyze_audio(
        client, settings, VOICE_NOTE_SYSTEM_PROMPT, pet_context or "(no additional pet background on file)", audio_b64, "mp3"
    )
