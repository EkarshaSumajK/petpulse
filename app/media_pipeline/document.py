"""Ports the document branch of `Media Router` (spec §2): image-mime
documents go straight to vision; everything else (PDF etc.) is rendered to
a page-1 image locally via PyMuPDF (see app.integrations.media_processing)
before vision analysis — no external service involved."""

import base64

from openai import AsyncOpenAI

from app.config import Settings
from app.integrations.media_processing import render_pdf_first_page
from app.integrations.openai_client import vision_completion
from app.media_pipeline.image import SYSTEM_PROMPT, analyze_image

PDF_SYSTEM_PROMPT = SYSTEM_PROMPT + (
    "\n\nThis image is page 1 of a scanned/photographed PDF document. Transcribe med names, dosages, "
    "lab values and ranges, dates, and diagnoses exactly as printed."
)


async def analyze_document(
    openai_client: AsyncOpenAI,
    settings: Settings,
    document_bytes: bytes,
    mime_type: str,
    caption: str,
) -> str:
    if mime_type.startswith("image/"):
        b64 = base64.b64encode(document_bytes).decode()
        return await analyze_image(openai_client, settings, b64, mime_type, caption)

    page_bytes = await render_pdf_first_page(document_bytes)
    page_b64 = base64.b64encode(page_bytes).decode()
    user_prompt = f"Owner/vet caption (if any): {caption or '(none)'}\n\nTranscribe page 1 of this document."
    return await vision_completion(
        openai_client, settings, PDF_SYSTEM_PROMPT, user_prompt, page_b64, "image/jpeg", max_tokens=1600
    )
