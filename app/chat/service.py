import json
from uuid import UUID

from fastapi import HTTPException
from openai import AsyncOpenAI

from app.chat.domain import ChatMessage
from app.chat.repository import ChatRepository
from app.moderation.service import ModerationService


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        llm_client: AsyncOpenAI,
        context_window: int = 10,
        default_model: str = "gpt-4o-mini",
    ):
        self.repository = repository
        self.llm_client = llm_client
        self.context_window = context_window
        self.default_model = default_model
        # LLM-клиент переиспользуется и для OpenAI Moderation API
        self.moderation = ModerationService(openai_client=llm_client)

    async def get_chat(self, chat_id: UUID):
        return await self.repository.get_chat(chat_id)

    async def send_message(
        self,
        chat_id: UUID,
        content: str,
        media_part: dict | None = None,
    ):
        # 0. Модерация входа — до сохранения и до LLM
        mod_in = await self.moderation.check_input(content or "")
        if not mod_in.allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "moderation_blocked",
                    "categories": mod_in.categories,
                },
            )

        # 1. Сохраняем user-сообщение
        user_msg = ChatMessage(
            chat_id=chat_id,
            role="user",
            content=content or "[медиа]",
            media_refs={"part": media_part} if media_part else None,
        )
        await self.repository.append_message(chat_id, user_msg)

        # 2. Собираем messages из истории
        messages = await self._build_messages(chat_id)

        # 3. Стрим через AsyncOpenAI
        stream = await self.llm_client.chat.completions.create(
            model=self.default_model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )

        full_response = ""
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_response += delta.content
                yield json.dumps(
                    {"type": "token", "delta": delta.content},
                    ensure_ascii=False,
                )

        # 4. Модерация выхода — перед сохранением и финальным done
        mod_out = await self.moderation.check_output(full_response)
        if not mod_out.allowed:
            # не сохраняем заблокированный ответ
            yield json.dumps(
                {
                    "type": "error",
                    "code": "moderation_blocked",
                    "categories": mod_out.categories,
                },
                ensure_ascii=False,
            )
            return  # без "done"

        # 5. Сохраняем ответ ассистента
        assistant_msg = ChatMessage(
            chat_id=chat_id,
            role="assistant",
            content=full_response,
        )
        await self.repository.append_message(chat_id, assistant_msg)

        # 6. Финальный фрейм
        yield json.dumps({"type": "done"})

    async def _build_messages(self, chat_id: UUID) -> list[dict]:
        history = await self.repository.list_messages(
            chat_id, limit=self.context_window
        )
        messages: list[dict] = []
        for msg in history:
            content = msg.content
            if msg.media_refs and msg.media_refs.get("part"):
                content = [
                    {"type": "text", "text": msg.content},
                    msg.media_refs["part"],
                ]
            messages.append({"role": msg.role, "content": content})
        return messages