from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(tags=["feedback"])


class FeedbackIn(BaseModel):
    message_id: str
    owner_external_id: int
    value: int


@router.post("/feedback")
async def save_feedback(
    body: FeedbackIn,
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        text("""
            INSERT INTO message_feedback (message_id, owner_external_id, value)
            VALUES (:message_id, :owner_external_id, :value)
            ON CONFLICT (owner_external_id, message_id) DO NOTHING
        """),
        {
            "message_id": body.message_id,
            "owner_external_id": body.owner_external_id,
            "value": body.value,
        },
    )
    await session.commit()
    return {"status": "ok"}