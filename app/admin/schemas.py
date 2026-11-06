# app/admin/schemas.py
from pydantic import BaseModel


class StatsOut(BaseModel):
    total_messages_24h: int
    active_users: int
    avg_latency_ms: float
    moderation_block_rate: float
    feedback_up_ratio: float


class UserOut(BaseModel):
    owner_external_id: str
    interface: str
    message_count: int = 0
    last_seen: str | None = None


class BroadcastBody(BaseModel):
    message: str
    interface_filter: str = "telegram"


class BroadcastResult(BaseModel):
    sent: int
    failed: int