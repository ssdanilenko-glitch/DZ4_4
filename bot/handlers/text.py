from aiogram import F, Router
from aiogram.types import Message

from bot.handlers.stream import stream_to_chat
from bot.services.backend_client import BackendClient
from bot.services.errors import humanize_backend_error
import structlog
logger = structlog.get_logger()

router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, backend: BackendClient) -> None:
    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, "telegram")

    try:
        tokens = backend.send_message(chat_id, message.text)
        await stream_to_chat(message, tokens)
    except Exception as exc:
        logger.exception("admin_cmd_failed", exc_info=exc)
        await message.answer(humanize_backend_error(exc))
