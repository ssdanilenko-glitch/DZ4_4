from io import BytesIO

from aiogram import F, Router
from aiogram.types import Message

from bot.services.backend_client import BackendClient
from bot.services.errors import humanize_backend_error
import structlog
logger = structlog.get_logger()

router = Router()

MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_DOC_BYTES = 10 * 1024 * 1024
ALLOWED_DOC_EXTENSIONS = (".pdf", ".docx")


@router.message(F.photo)
async def handle_photo(message: Message, backend: BackendClient) -> None:
    # Выбираем размер ≤ 2 МБ, иначе — наибольший доступный
    candidates = [p for p in message.photo if (p.file_size or 0) <= MAX_PHOTO_BYTES]
    photo = candidates[-1] if candidates else message.photo[-1]

    file = await message.bot.get_file(photo.file_id)
    data = await message.bot.download_file(file.file_path)
    raw = data.getvalue() if hasattr(data, "getvalue") else bytes(data)

    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, "telegram")

    await _stream_and_reply(
        message, backend, chat_id,
        content=message.caption or "[фото]",
        media=raw,
        mime="image/jpeg",
    )


@router.message(F.voice)
async def handle_voice(message: Message, backend: BackendClient) -> None:
    file = await message.bot.get_file(message.voice.file_id)
    data = await message.bot.download_file(file.file_path)
    raw = data.getvalue() if hasattr(data, "getvalue") else bytes(data)

    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, "telegram")

    await _stream_and_reply(
        message, backend, chat_id,
        content=message.caption or "[голосовое]",
        media=raw,
        mime="audio/ogg",
    )


@router.message(
    F.document,
    F.document.file_name.func(lambda n: n and n.lower().endswith(ALLOWED_DOC_EXTENSIONS)),
    F.document.file_size.func(lambda s: s is not None and s <= MAX_DOC_BYTES),
)
async def handle_document(message: Message, backend: BackendClient) -> None:
    doc = message.document
    file = await message.bot.get_file(doc.file_id)
    data = await message.bot.download_file(file.file_path)
    raw = data.getvalue() if hasattr(data, "getvalue") else bytes(data)

    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, "telegram")

    await _stream_and_reply(
        message, backend, chat_id,
        content=message.caption or f"[документ: {doc.file_name}]",
        media=raw,
        mime=doc.mime_type or "application/octet-stream",
    )


async def _stream_and_reply(
    message: Message,
    backend: BackendClient,
    chat_id,
    content: str,
    media: bytes,
    mime: str,
) -> None:
    from bot.handlers.stream import stream_to_chat

    try:
        tokens = backend.send_message(chat_id, content, media=media, mime=mime)
        await stream_to_chat(message, tokens)
    except Exception as exc:
        logger.exception("admin_cmd_failed", exc_info=exc)
        await message.answer(humanize_backend_error(exc))
