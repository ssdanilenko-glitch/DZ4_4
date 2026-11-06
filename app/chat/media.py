import base64
from io import BytesIO

from fastapi import UploadFile
from openai import AsyncOpenAI
from pypdf import PdfReader
from docx import Document

from app.core.config import get_settings

settings = get_settings()

client = AsyncOpenAI(
    api_key=settings.llm.openai_api_key.get_secret_value(),
    base_url=settings.llm.base_url,
)

MAX_TEXT_CHARS = 30_000


async def media_to_part(media: UploadFile) -> dict:
    mime = media.content_type or ""
    data = await media.read()

    if mime.startswith("image/"):
        b64 = base64.b64encode(data).decode()
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        }

    if mime.startswith("audio/") or mime == "application/ogg":
        transcript = await whisper_transcribe(data, media.filename or "audio.ogg")
        return {
            "type": "text",
            "text": f"[пользователь сказал голосом]:\n{transcript}",
        }

    if mime == "application/pdf":
        return {
            "type": "text",
            "text": f"[документ PDF]:\n{extract_pdf_text(data)[:MAX_TEXT_CHARS]}",
        }

    if mime.endswith("wordprocessingml.document"):
        return {
            "type": "text",
            "text": f"[документ DOCX]:\n{extract_docx_text(data)[:MAX_TEXT_CHARS]}",
        }

    raise ValueError(f"Unsupported media type: {mime}")


async def whisper_transcribe(audio_bytes: bytes, filename: str) -> str:
    """Whisper-1 принимает ogg/m4a/mp3/wav/flac/webm напрямую."""
    f = BytesIO(audio_bytes)
    f.name = filename  # SDK берёт расширение для определения формата
    result = await client.audio.transcriptions.create(
        model="whisper-1",
        file=f,
    )
    return result.text


def extract_pdf_text(data: bytes, max_pages: int = 50) -> str:
    reader = PdfReader(BytesIO(data))
    pages = reader.pages[:max_pages]
    texts = [page.extract_text() or "" for page in pages]
    result = "\n".join(texts).strip()

    # Эвристика скана: мало символов на многих страницах
    if len(pages) >= 5 and len(result) < 100:
        return "[PDF похож на скан, текст не извлечён]"
    return result


def extract_docx_text(data: bytes) -> str:
    doc = Document(BytesIO(data))
    parts: list[str] = []

    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text)

    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return "\n".join(parts).strip()