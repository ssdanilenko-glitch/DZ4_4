# app/chat/repositories/pg_models.py
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text

TimestampTZ = DateTime(timezone=True)


from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass


class ChatRow(Base):
    __tablename__ = "chats"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_external_id: Mapped[str] = mapped_column(String, nullable=False)
    interface: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, default=lambda: datetime.now(UTC))


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    chat_id: Mapped[UUID] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    media_refs: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # <-- НОВОЕ
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, default=lambda: datetime.now(UTC))
    deleted_at: Mapped[datetime | None] = mapped_column(TimestampTZ, nullable=True)