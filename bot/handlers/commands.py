from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.services.backend_client import BackendClient

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, backend: BackendClient):
    owner_id = str(message.from_user.id)
    chat = await backend.get_or_create_chat(owner_id, "telegram")
    await message.answer(
        f"Привет! Чат создан (ID: `{chat}`).\n"
        "Просто напиши сообщение — я передам его в LLM.\n"
        "/help — команды\n/clear — очистить историю\n/ask — сценарий с темой"
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "/start — начать\n"
        "/help — эта справка\n"
        "/clear — очистить историю\n"
        "/ask — задать вопрос по теме\n"
        "/cancel — отменить сценарий"
    )

@router.message(Command("clear"))
async def cmd_clear(message: Message, backend: BackendClient):
    owner_id = str(message.from_user.id)
    chat = await backend.get_or_create_chat(owner_id, "telegram")
    await backend.clear_messages(chat)
    await message.answer("История очищена.")

# /cancel регистрируется ПЕРВЫМ среди FSM-хендлеров
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Сценарий отменён.")