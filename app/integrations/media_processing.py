"""Local video-frame / PDF-page extraction — replaces the earlier
Cloudinary-based pipeline (spec §5). Video frame + audio-track extraction
via ffmpeg (subprocess); PDF page-1 rendering via PyMuPDF (pure-Python
wheel, no extra system dependency). No external media service or
credential needed; ffmpeg must be present on the host (see Dockerfile)."""

import asyncio
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF


def _run_ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)


def _extract_video_frame_sync(video_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "input.mp4"
        frame_path = Path(tmp) / "frame.jpg"
        video_path.write_bytes(video_bytes)
        _run_ffmpeg(["-i", str(video_path), "-vframes", "1", "-f", "image2", str(frame_path)])
        return frame_path.read_bytes()


def _extract_video_audio_sync(video_bytes: bytes) -> bytes | None:
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "input.mp4"
        audio_path = Path(tmp) / "audio.mp3"
        video_path.write_bytes(video_bytes)
        try:
            _run_ffmpeg(["-i", str(video_path), "-vn", "-acodec", "libmp3lame", str(audio_path)])
        except subprocess.CalledProcessError:
            return None  # video has no audio track
        return audio_path.read_bytes()


def _render_pdf_first_page_sync(pdf_bytes: bytes) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[0]
        pixmap = page.get_pixmap(dpi=200)
        return pixmap.tobytes("jpg")
    finally:
        doc.close()


async def extract_video_frame(video_bytes: bytes) -> bytes:
    return await asyncio.to_thread(_extract_video_frame_sync, video_bytes)


async def extract_video_audio(video_bytes: bytes) -> bytes | None:
    return await asyncio.to_thread(_extract_video_audio_sync, video_bytes)


async def render_pdf_first_page(pdf_bytes: bytes) -> bytes:
    return await asyncio.to_thread(_render_pdf_first_page_sync, pdf_bytes)
