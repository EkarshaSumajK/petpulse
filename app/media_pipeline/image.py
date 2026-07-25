"""Ports `Analyze Image With AI` (spec §2): a single vision call that first
decides pet-photo-vs-document, then either describes visible health signs
or transcribes a document faithfully (vaccine names incl. sticker brand
names, batch/lot numbers, all dates, clinic/vet info, microchip, explicit
handwritten-vs-printed flag per field, marks illegible fields rather than
guessing)."""

from openai import AsyncOpenAI

from app.config import Settings
from app.integrations.openai_client import vision_completion

SYSTEM_PROMPT = """You are analyzing an image sent by a pet owner or vet over WhatsApp to a \
veterinary assistant. First decide: is this a casual photo of a pet, or a document (vaccination \
certificate, prescription, lab report, ID card, etc.)?

If it's a pet photo: describe what's visible relevant to health (posture, coat, visible wounds, \
eyes, gait, weight/body condition) in 2-4 sentences. Do not invent a diagnosis. You may be given \
background on the pet's known chronic conditions/allergies — use it only to sharpen your description \
(e.g. noting a visible sign is consistent with a known condition), never to claim something isn't \
actually visible.

If it's a document: transcribe it faithfully. Include every vaccine name (including sticker brand \
names), batch/lot numbers, all dates, clinic/vet name and contact info, microchip number if present. \
For each field, explicitly note whether it is handwritten or printed. If a field is illegible, say \
"illegible" rather than guessing its value. Never fabricate a date, name, or number that isn't \
clearly visible."""


async def analyze_image(
    client: AsyncOpenAI, settings: Settings, image_base64: str, mime_type: str, caption: str, pet_context: str = ""
) -> str:
    user_prompt = f"{pet_context}Owner/vet caption (if any): {caption or '(none)'}\n\nAnalyze the attached image."
    return await vision_completion(client, settings, SYSTEM_PROMPT, user_prompt, image_base64, mime_type)
