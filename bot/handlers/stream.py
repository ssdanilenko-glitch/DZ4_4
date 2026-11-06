import asyncio
import time
import uuid

from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message

from bot.keyboards.feedback import feedback_keyboard

MIN_INTERVAL = 0.8


async def stream_to_chat(message: Message, tokens) -> int | None:
    """Стримит ответ и возвращает message_id финального ответа (или None)."""
    draft_id = uuid.uuid4().int & 0xFFFFFFFF
    buffer = ""
    last_sent = 0.0

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    await message.bot.send_message_draft(
        chat_id=message.chat.id, draft_id=draft_id, text="",
    )

    async for delta in tokens:
        buffer += delta
        now = time.monotonic()
        if buffer.strip() and (now - last_sent) >= MIN_INTERVAL:
            try:
                await message.bot.send_message_draft(
                    chat_id=message.chat.id, draft_id=draft_id, text=buffer,
                )
                last_sent = now
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)

    if not buffer:
        return None

    sent = await message.bot.send_message(
        chat_id=message.chat.id,
        text=buffer,
        reply_markup=feedback_keyboard(str(message.message_id)),  # или str(sent.message_id)
    )
    return sent.message_id