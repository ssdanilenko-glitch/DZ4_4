"""HTTP-роуты chat-модуля (Б4.3: медиа + JSON-SSE + обратный канал; Б4.4: модерация)."""
import json
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.chat.deps import get_chat_service
from app.chat.domain import Chat, ChatMessage
from app.chat.media import media_to_part
from app.chat.service import ChatService
from app.services.notifier import notify_user

router = APIRouter(prefix="/chats", tags=["chats"])


class CreateChatIn(BaseModel):
    owner_external_id: str
    interface: str
    system_prompt: str | None = None


class CreateChatOut(BaseModel):
    chat_id: UUID


class SystemMessageIn(BaseModel):
    text: str
    notify: bool = False


@router.post("", response_model=CreateChatOut)
async def create_chat(
    body: CreateChatIn,
    chat_service: ChatService = Depends(get_chat_service),
) -> CreateChatOut:
    chat = await chat_service.repository.create_chat(
        owner_external_id=body.owner_external_id,
        interface=body.interface,
        system_prompt=body.system_prompt,
    )
    return CreateChatOut(chat_id=chat.id)


@router.get("/{chat_id}", response_model=Chat)
async def get_chat(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
) -> Chat:
    chat = await chat_service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: UUID,
    content: str = Form(...),
    media: UploadFile | None = File(None),
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    chat = await chat_service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")

    # Б4.4: входная модерация ДО стрима — 403 вернётся обычным JSON
    mod_in = await chat_service.moderation.check_input(content or "")
    if not mod_in.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "moderation_blocked",
                "categories": mod_in.categories,
            },
        )

    media_part = None
    if media is not None:
        try:
            media_part = await media_to_part(media)
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc

    async def event_generator():
        try:
            async for chunk in chat_service.send_message(
                chat_id, content, media_part=media_part
            ):
                yield f"data: {chunk}\n\n"
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            yield (
                "data: "
                + json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
                + "\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.get("/{chat_id}/messages", response_model=list[ChatMessage])
async def list_messages(
    chat_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    chat_service: ChatService = Depends(get_chat_service),
) -> list[ChatMessage]:
    chat = await chat_service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return await chat_service.repository.list_messages(chat_id, limit=limit)


@router.delete("/{chat_id}/messages")
async def delete_messages(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
) -> dict:
    chat = await chat_service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    await chat_service.repository.soft_delete_messages(chat_id)
    return {"status": "ok"}


@router.post("/{chat_id}/system-message")
async def system_message(
    chat_id: UUID,
    body: SystemMessageIn,
    chat_service: ChatService = Depends(get_chat_service),
) -> dict:
    chat = await chat_service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")

    msg = ChatMessage(chat_id=chat_id, role="assistant", content=body.text)
    await chat_service.repository.append_message(chat_id, msg)

    if body.notify:
        try:
            tg_id = int(chat.owner_external_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail="owner_external_id is not a valid telegram id",
            ) from exc
        await notify_user(tg_id, body.text)

    return {"status": "ok"}