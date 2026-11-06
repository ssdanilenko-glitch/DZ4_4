import json
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from uuid import uuid4

from app.main import app
from app.chat.deps import get_chat_service, get_repository
from app.chat.service import ChatService
from app.chat.repositories.json_repo import JsonChatRepository
from app.core.config import get_settings
from unittest.mock import MagicMock
pytestmark = pytest.mark.asyncio


# Переопределяем зависимости для тестов (используем JSON-репозиторий с временной директорией)
@pytest.fixture
def test_app(tmp_path):
    # Создаём тестовое приложение с переопределёнными зависимостями
    app.dependency_overrides = {}

    # Создаём репозиторий
    repo = JsonChatRepository(tmp_path / "chats")

    # Создаём LLM клиент-заглушку
    from unittest.mock import AsyncMock, MagicMock
    mock_llm = AsyncMock()
    mock_llm.chat.completions.create.side_effect = lambda **kwargs: create_mock_stream(["Hello", " ", "world"])

    # Переопределяем get_chat_service
    async def override_get_chat_service():
        settings = get_settings()
        return ChatService(repo, mock_llm, context_window=settings.chat_context_window)

    app.dependency_overrides[get_chat_service] = override_get_chat_service
    app.dependency_overrides[get_repository] = lambda: repo
    app.state.redis = None
    return app


async def test_create_chat(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chats",
            json={"owner_external_id": "user123", "interface": "web", "system_prompt": "You are helpful"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        chat_id = data["chat_id"]

        # Проверяем, что чат существует
        resp = await client.get(f"/chats/{chat_id}")
        assert resp.status_code == 200
        chat = resp.json()
        assert chat["owner_external_id"] == "user123"


async def test_send_message_streaming(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Создаём чат
        resp = await client.post("/chats", json={"owner_external_id": "user", "interface": "web"})
        chat_id = resp.json()["chat_id"]

        # Отправляем сообщение с SSE
        async with client.stream(
            "POST",
            f"/chats/{chat_id}/messages",
            json={"content": "Hello"}
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            # Читаем события
            events = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(line[6:])
            # Проверяем, что последнее событие [DONE]
            assert events[-1] == "[DONE]"
            # Проверяем, что есть токены
            assert len(events) > 1
            # Первые события должны быть данными
            assert events[0] == "Hello"
            assert events[1] == " "
            assert events[2] == "world"


async def test_list_messages(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Создаём чат
        resp = await client.post("/chats", json={"owner_external_id": "user", "interface": "web"})
        chat_id = resp.json()["chat_id"]

        # Отправляем два сообщения
        await client.post(f"/chats/{chat_id}/messages", json={"content": "Hi"})
        await client.post(f"/chats/{chat_id}/messages", json={"content": "How are you?"})

        # Получаем историю
        resp = await client.get(f"/chats/{chat_id}/messages?limit=10")
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) == 4  # 2 user + 2 assistant
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hi"
        assert msgs[1]["role"] == "assistant"
        assert msgs[2]["role"] == "user"
        assert msgs[2]["content"] == "How are you?"


async def test_delete_messages(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/chats", json={"owner_external_id": "user", "interface": "web"})
        chat_id = resp.json()["chat_id"]

        # Добавим сообщение
        await client.post(f"/chats/{chat_id}/messages", json={"content": "Hello"})

        # Удаляем
        resp = await client.delete(f"/chats/{chat_id}/messages")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        # Проверяем, что история пуста
        resp = await client.get(f"/chats/{chat_id}/messages")
        msgs = resp.json()
        assert len(msgs) == 0

        # Новое сообщение должно быть видно
        await client.post(f"/chats/{chat_id}/messages", json={"content": "New"})
        resp = await client.get(f"/chats/{chat_id}/messages")
        msgs = resp.json()
        assert len(msgs) == 2  # user + assistant
        assert msgs[0]["content"] == "New"  # user
        assert msgs[1]["role"] == "assistant"


async def test_get_chat_404(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/chats/{uuid4()}")
        assert resp.status_code == 404


async def test_delete_messages_404(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(f"/chats/{uuid4()}/messages")
        assert resp.status_code == 404


# Вспомогательная функция для мок-стрима (дублируется из test_service_context)
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