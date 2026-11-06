# bot/__main__.py
import asyncio
import os

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession   # <-- добавить
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers import setup_routers
from bot.services.backend_client import BackendClient
from bot.web import build_api


async def main() -> None:
    # Прокси для Telegram (из .env или захардкоженный)
    proxy_url = os.getenv("TELEGRAM_PROXY_URL", "http://local_user:p32kcF26NhWE@72.56.89.38:8888")
    session = AiohttpSession(proxy=proxy_url)               # <-- ключевая строка

    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,                                     # <-- передать сессию
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher(storage=MemoryStorage())

    backend = BackendClient()
    dp["backend"] = backend
    dp.include_router(setup_routers())

    api = build_api(bot, settings.INTERNAL_TOKEN)
    config = uvicorn.Config(api, host="0.0.0.0", port=settings.BOT_API_PORT, log_level="info")
    server = uvicorn.Server(config)

    try:
        await asyncio.gather(dp.start_polling(bot), server.serve())
    finally:
        await backend.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())