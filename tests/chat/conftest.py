import pytest
import pytest_asyncio
from pathlib import Path
from typing import AsyncIterator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# ГАРАНТИРУЕМ регистрацию моделей – импортируем модуль целиком
from app.chat.repositories import pg_models
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository
from app.chat.repositories.pg_models import Base
from app.chat.repository import ChatRepository

from testcontainers.postgres import PostgresContainer

@pytest_asyncio.fixture
async def json_repo(tmp_path: Path) -> AsyncIterator[JsonChatRepository]:
    repo = JsonChatRepository(tmp_path / "chats")
    yield repo


@pytest_asyncio.fixture
async def pg_repo():
    # Подключаемся к БД из docker-compose
    DATABASE_URL = "postgresql+asyncpg://test_user:test_password@localhost:5433/test_db"
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_maker() as session:
        yield PostgresChatRepository(session)


@pytest.fixture(params=["json", "postgres"])
def repo(request, json_repo, pg_repo) -> ChatRepository:
    if request.param == "json":
        return json_repo
    return pg_repo


# ----- Фикстуры для тестов сервиса -----

@pytest_asyncio.fixture
async def mock_repo() -> AsyncIterator[ChatRepository]:
    from uuid import UUID, uuid4
    from datetime import datetime, timezone
    from app.chat.domain import Chat, ChatMessage

    class FakeRepo:
        def __init__(self):
            self.chats: dict[UUID, Chat] = {}
            self.messages: dict[UUID, list[ChatMessage]] = {}
            self.deleted_markers: dict[UUID, datetime] = {}

        async def create_chat(self, owner_external_id: str, interface: str,
                              system_prompt: str | None = None) -> Chat:
            chat = Chat(
                id=uuid4(),
                owner_external_id=owner_external_id,
                interface=interface,
                system_prompt=system_prompt,
                created_at=datetime.now(timezone.utc)
            )
            self.chats[chat.id] = chat
            self.messages[chat.id] = []
            return chat

        async def get_chat(self, chat_id: UUID) -> Chat | None:
            return self.chats.get(chat_id)

        async def append_message(self, chat_id: UUID, message: ChatMessage) -> ChatMessage:
            if chat_id not in self.messages:
                self.messages[chat_id] = []
            self.messages[chat_id].append(message)
            return message

        async def list_messages(self, chat_id: UUID, limit: int = 50) -> list[ChatMessage]:
            msgs = self.messages.get(chat_id, [])
            if chat_id in self.deleted_markers:
                marker_time = self.deleted_markers[chat_id]
                msgs = [m for m in msgs if m.created_at > marker_time]
            return msgs[-limit:] if limit else msgs

        async def soft_delete_messages(self, chat_id: UUID) -> None:
            self.deleted_markers[chat_id] = datetime.now(timezone.utc)

    return FakeRepo()


@pytest.fixture
def mock_llm():
    from unittest.mock import AsyncMock, MagicMock

    class AsyncIteratorMock:
        def __init__(self, chunks):
            self.chunks = chunks
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.index >= len(self.chunks):
                raise StopAsyncIteration
            chunk = self.chunks[self.index]
            self.index += 1
            return chunk

    def create_mock_stream(text_chunks):
        class MockChunk:
            def __init__(self, content):
                self.choices = [MagicMock(delta=MagicMock(content=content))]
        return AsyncIteratorMock([MockChunk(chunk) for chunk in text_chunks])

    llm = AsyncMock()
    llm.chat.completions.create.side_effect = lambda **kwargs: create_mock_stream(["Hello", " ", "world"])
    return llm

