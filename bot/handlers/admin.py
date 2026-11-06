import httpx
from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from bot.config import get_settings        # ✅ из bot
from bot.services.errors import humanize_backend_error
import structlog
logger = structlog.get_logger()
admin_router = Router()


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in get_settings().BOT_ADMIN_IDS


# фильтр на уровне роутера — до всех handler'ов
admin_router.message.filter(IsAdmin())


def _headers() -> dict:
    return {"X-Admin-Token": get_settings().ADMIN_TOKEN}


def _base() -> str:
    return get_settings().BACKEND_URL.rstrip("/")


@admin_router.message(Command("stats"))
async def cmd_stats(message: Message):
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{_base()}/chats/admin/stats", headers=_headers())
            r.raise_for_status()
            d = r.json()
        await message.answer(
            f"📊 Статистика (24ч)\n"
            f"Сообщений: {d['total_messages_24h']}\n"
            f"DAU: {d['active_users']}\n"
            f"Ср. latency: {d['avg_latency_ms']:.0f} ms\n"
            f"Блокировок: {d['moderation_block_rate']:.2%}\n"
            f"👍 ratio: {d['feedback_up_ratio']:.2%}"
        )
    except Exception as exc:
        logger.exception("admin_cmd_failed", exc_info=exc)
        await message.answer(humanize_backend_error(exc))


@admin_router.message(Command("users"))
async def cmd_users(message: Message):
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{_base()}/chats/admin/users?limit=50", headers=_headers()
            )
            r.raise_for_status()
            users = r.json()
        if not users:
            await message.answer("👥 Пользователей нет.")
            return
        lines = [
            f"`{u['owner_external_id']}` ({u['interface']}) — {u['message_count']} сообщ."
            for u in users[:20]
        ]
        await message.answer(
            "👥 Пользователи (топ-20):\n" + "\n".join(lines),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("admin_cmd_failed", exc_info=exc)
        await message.answer(humanize_backend_error(exc))


@admin_router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    text = (message.text or "").removeprefix("/broadcast").strip()
    if not text:
        await message.answer("Использование: /broadcast <текст>")
        return
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{_base()}/chats/admin/broadcast",
                json={"message": text, "interface_filter": "telegram"},
                headers=_headers(),
            )
            r.raise_for_status()
            d = r.json()
        await message.answer(f"📣 Отправлено: {d['sent']}, ошибок: {d['failed']}")
    except Exception as exc:
        logger.exception("admin_cmd_failed", exc_info=exc)
        await message.answer(humanize_backend_error(exc))