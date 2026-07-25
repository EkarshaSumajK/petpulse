"""Ports `Detect Message Type` -> `Media Router` (spec §2): routes an
inbound message to the right media_pipeline analyzer and produces both a
plain-text `media_context` for the agent prompt and, for image/document
messages, a `DocumentClassification` the agent can act on via the
`file_document` tool."""

from dataclasses import dataclass

from app.deps import AppContext
from app.ingestion.webhook import ExtractedMessage
from app.media_pipeline import audio as audio_pipeline
from app.media_pipeline import document as document_pipeline
from app.media_pipeline import image as image_pipeline
from app.media_pipeline import video as video_pipeline
from app.media_pipeline.classify import DocumentClassification, classify_document


@dataclass
class MediaResult:
    media_context: str = ""
    document_classification: DocumentClassification | None = None
    document_bytes: bytes | None = None
    document_mime_type: str | None = None


async def process_media(ctx: AppContext, extracted: ExtractedMessage, pets: list[dict]) -> MediaResult:
    if extracted.image_media_id:
        data, mime = await ctx.whatsapp.download_media_bytes(extracted.image_media_id)
        import base64

        analysis = await image_pipeline.analyze_image(
            ctx.openai, ctx.settings, base64.b64encode(data).decode(), mime, extracted.text
        )
        classification = await classify_document(
            ctx.openai, ctx.settings, "image", mime, analysis, extracted.text, pets
        )
        return MediaResult(
            media_context=f"[Image analysis] {analysis}",
            document_classification=classification,
            document_bytes=data,
            document_mime_type=mime,
        )

    if extracted.audio_media_id:
        data, mime = await ctx.whatsapp.download_media_bytes(extracted.audio_media_id)
        transcript = await audio_pipeline.analyze_voice_note(ctx.openai, data)
        return MediaResult(media_context=f"[Voice note transcript] {transcript}")

    if extracted.document_media_id:
        data, mime = await ctx.whatsapp.download_media_bytes(extracted.document_media_id)
        mime = extracted.document_mime_type or mime
        analysis = await document_pipeline.analyze_document(ctx.openai, ctx.settings, data, mime, extracted.text)
        classification = await classify_document(
            ctx.openai, ctx.settings, "document", mime, analysis, extracted.text, pets
        )
        return MediaResult(
            media_context=f"[Document analysis] {analysis}",
            document_classification=classification,
            document_bytes=data,
            document_mime_type=mime,
        )

    if extracted.video_media_id:
        data, mime = await ctx.whatsapp.download_media_bytes(extracted.video_media_id)
        analysis = await video_pipeline.analyze_video(ctx.openai, ctx.settings, data, extracted.text)
        classification = await classify_document(
            ctx.openai, ctx.settings, "video", mime, analysis, extracted.text, pets
        )
        return MediaResult(
            media_context=analysis,
            document_classification=classification,
            document_bytes=data,
            document_mime_type=mime,
        )

    return MediaResult()
