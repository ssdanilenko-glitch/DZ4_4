from aiogram import Router
from bot.handlers.admin import admin_router

from . import commands, fsm, media, text
from bot.handlers.feedback import router as feedback_router

def setup_routers() -> Router:
    router = Router()
    router.include_router(admin_router)
    router.include_router(commands.router)
    router.include_router(fsm.router)
    router.include_router(media.router)   # до text — иначе F.text перехватит
    router.include_router(text.router)
    router.include_router(feedback_router)
    return router