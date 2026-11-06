import os

import httpx
from aiogram import F, Router
from aiogram.types import CallbackQuery

import structlog
logger = structlog.get_logger()

router = Router()


def _base() -> str:
    return os.getenv("BACKEND_URL", "http://app:8000").rstrip("/")


@router.callback_query(F.data.startswith("fb:"))
async def handle_feedback(callback: CallbackQuery):
    try:
        _, vote, message_id = callback.data.split(":", 2)
    except ValueError:
        await callback.answer("Некорректные данные")
        return

    value = 1 if vote == "up" else -1

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(
                f"{_base()}/feedback",
                json={
                    "message_id": message_id,
                    "owner_external_id": callback.from_user.id,
                    "value": value,
                },
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.exception("feedback_failed", exc_info=exc)
        await callback.answer("Не удалось сохранить")
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Спасибо!")