# app/chat/deps.py
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository
from app.chat.repository import ChatRepository
from app.chat.service import ChatService
from app.core.config import get_settings
from app.core.database import async_session_maker


async def get_repository() -> AsyncIterator[ChatRepository]:
    settings = get_settings()
    if settings.chat_repository == "json":
        yield JsonChatRepository(settings.chat_storage_dir)
        return

    if settings.chat_repository == "postgres":
        async with async_session_maker() as session:
            yield PostgresChatRepository(session)
        return

    raise ValueError(f"unknown chat_repository: {settings.chat_repository}")


RepositoryDep = Annotated[ChatRepository, Depends(get_repository)]


def get_llm_client(request: Request):
    return request.app.state.llm


LLMDep = Annotated[type, Depends(get_llm_client)]  # type: ignore


def get_chat_service(
    repo: RepositoryDep,
    llm: LLMDep,
) -> ChatService:
    settings = get_settings()
    return ChatService(
        repository=repo,
        llm_client=llm,
        context_window=settings.chat_context_window,
        default_model=settings.llm.default_model,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]