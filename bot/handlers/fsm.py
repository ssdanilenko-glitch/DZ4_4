from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.stream import stream_to_chat
from bot.keyboards.inline import topics_kb
from bot.services.backend_client import BackendClient
from bot.states import AskFlow
from bot.services.errors import humanize_backend_error
import structlog
logger = structlog.get_logger()

router = Router()


@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext) -> None:
    await state.set_state(AskFlow.waiting_for_topic)
    await message.answer("Выбери тему:", reply_markup=topics_kb())


@router.callback_query(F.data.startswith("topic:"), AskFlow.waiting_for_topic)
async def on_topic(callback: CallbackQuery, state: FSMContext) -> None:
    slug = callback.data.split(":", 1)[1]
    if slug == "cancel":
        await state.clear()
        await callback.message.edit_text("Отменено.")
        await callback.answer()
        return
    await state.update_data(topic=slug)
    await state.set_state(AskFlow.waiting_for_question)
    await callback.message.edit_text(f"Тема: {slug}.\nТеперь напиши свой вопрос.")
    await callback.answer()


@router.message(AskFlow.waiting_for_question, F.text)
async def on_question(
    message: Message, state: FSMContext, backend: BackendClient
) -> None:
    data = await state.get_data()
    topic = data.get("topic", "общее")
    prompt = f"Тема: {topic}. Вопрос: {message.text}"

    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, "telegram")

    try:
        tokens = backend.send_message(chat_id, prompt)
        await stream_to_chat(message, tokens)
    except Exception as exc:
        logger.exception("admin_cmd_failed", exc_info=exc)
        await message.answer(humanize_backend_error(exc))
    finally:
        await state.clear()