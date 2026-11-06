import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import CallbackQuery

from bot.handlers.fsm import on_topic
from bot.states import AskFlow

@pytest.mark.asyncio
async def test_on_topic_transitions_to_question():
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=AskFlow.waiting_for_topic)

    callback = MagicMock(spec=CallbackQuery)
    callback.data = "topic:billing"
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock() # Явно указываем, что это асинхронный вызов
    callback.answer = AsyncMock()

    await on_topic(callback, state)

    state.update_data.assert_awaited_once_with(topic="billing")
    state.set_state.assert_awaited_once_with(AskFlow.waiting_for_question)
    callback.message.edit_text.assert_awaited_once()