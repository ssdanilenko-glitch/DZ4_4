import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.chat.domain import ChatMessage
from app.chat.service import ChatService
from app.core.config import get_settings

pytestmark = pytest.mark.asyncio


async def test_create_chat(mock_repo, mock_llm):
    service = ChatService(mock_repo, mock_llm)
    chat = await service.create_chat("user", "web", "system")
    assert chat.id is not None
    assert chat.owner_external_id == "user"


async def test_send_message_saves_user_and_assistant(mock_repo, mock_llm):
    service = ChatService(mock_repo, mock_llm, context_window=10)
    chat = await service.create_chat("user", "web", "You are helpful")

    # Мокаем ответ LLM: "Hello world"
    mock_llm.chat.completions.create.return_value = create_mock_stream(["Hello", " ", "world"])

    chunks = []
    async for chunk in service.send_message(chat.id, "Hi"):
        chunks.append(chunk)
    assert "".join(chunks) == "Hello world"

    # Проверяем, что сообщения сохранились
    msgs = await mock_repo.list_messages(chat.id)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "Hi"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "Hello world"


async def test_send_message_includes_system_prompt(mock_repo, mock_llm):
    service = ChatService(mock_repo, mock_llm, context_window=10)
    chat = await service.create_chat("user", "web", "You are a pirate")

    # Проверяем, что системный промпт передан в LLM
    await service.send_message(chat.id, "Ahoy!").__anext__()  # потребляем первый chunk

    # Проверяем, что create был вызван с правильными messages
    call_args = mock_llm.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a pirate"


async def test_send_message_uses_context_window(mock_repo, mock_llm):
    service = ChatService(mock_repo, mock_llm, context_window=3)
    chat = await service.create_chat("user", "web")

    # Добавляем 5 сообщений вручную через репозиторий
    for i in range(5):
        msg = ChatMessage(chat_id=chat.id, role="user", content=f"msg{i}")
        await mock_repo.append_message(chat.id, msg)

    # Отправляем новое сообщение
    await service.send_message(chat.id, "last").__anext__()

    # Проверяем, что в контекст попали только последние 3 (плюс новое?)
    # Сначала сохраняется user-сообщение "last", затем загружается история с limit=3
    # Итоговые сообщения для LLM: system (если есть) + последние 3 истории + новое user
    call_args = mock_llm.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    # Должно быть 4 сообщения: последние 3 истории + новое user
    # (без system, так как system_prompt=None)
    assert len(messages) == 3
    # Порядок: от старых к новым
    assert messages[0]["content"] == "msg3"
    assert messages[1]["content"] == "msg4"
    assert messages[2]["content"] == "last"


async def test_fit_to_budget_trims_context(mock_repo, mock_llm, monkeypatch):
    # Подменяем настройки для маленького бюджета
    settings = get_settings()
    monkeypatch.setattr(settings, "context_window_tokens", 20)  # маленький
    monkeypatch.setattr(settings, "response_tokens", 5)
    monkeypatch.setattr(settings, "safety_margin", 2)
    service = ChatService(mock_repo, mock_llm, context_window=10)
    chat = await service.create_chat("user", "web", "System prompt")

    # Добавим много сообщений
    for i in range(10):
        msg = ChatMessage(chat_id=chat.id, role="user", content=f"x" * 10)  # каждое ~10 токенов
        await mock_repo.append_message(chat.id, msg)

    # Отправляем сообщение
    await service.send_message(chat.id, "last").__anext__()

    # Проверяем, что в LLM отправлены только системное + последние несколько сообщений
    call_args = mock_llm.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    # Системное должно быть всегда
    assert messages[0]["role"] == "system"
    # Остальные сообщения должны быть обрезаны по бюджету
    # Т.к. бюджет маленький, должно остаться только system и, возможно, одно сообщение
    # Но точное число зависит от токенов, проверим, что общее количество <= budget
    from app.chat.context import count_tokens
    token_count = count_tokens(messages)
    budget = settings.context_window_tokens - settings.response_tokens - settings.safety_margin
    assert token_count <= budget


# Вспомогательная функция для создания мок-стрима
def create_mock_stream(text_chunks):
    class AsyncIteratorMock:
        def __init__(self, chunks):
            self.chunks = chunks
            self.index = 0
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self.index >= len(self.chunks):
                raise StopAsyncIteration
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content=self.chunks[self.index]))]
            self.index += 1
            return chunk
    return AsyncIteratorMock(text_chunks)