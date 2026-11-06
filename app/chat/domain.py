"""Доменные модели чата.

Чистые Pydantic v2-модели — никаких импортов из SQLAlchemy / FastAPI / aiofiles.
Доменные модели чата."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["user", "assistant", "system"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    chat_id: UUID
    role: Role
    content: str
    media_refs: dict | None = None
    prompt_id: UUID | None = None
    tokens: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Chat(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    owner_external_id: str
    interface: str
    system_prompt: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

