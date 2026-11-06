# app/admin/routes.py
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends

from app.admin.deps import require_admin
from app.admin.schemas import (
    BroadcastBody,
    BroadcastResult,
    StatsOut,
    UserOut,
)
from app.core.config import get_settings
from app.services.notifier import notify_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chats/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


def _chats_dir() -> Path:
    # Путь совпадает с тем, что пишет ChatRepository (из Б4.1–Б4.3)
    settings = get_settings()
    base = getattr(settings, "CHATS_DIR", None) or "/app/var/chats"
    return Path(base)


def _iter_chats():
    base = _chats_dir()
    if not base.exists():
        return
    for chat_dir in base.iterdir():
        if not chat_dir.is_dir():
            continue
        meta_path = chat_dir / "chat.json"
        if not meta_path.exists():
            meta_path = chat_dir / "meta.json"  # фолбэк на случай других форматов
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not meta.get("id"):
            meta["id"] = chat_dir.name
        yield meta



def _iter_messages(chat_dir: Path):
    file = chat_dir / "messages.jsonl"
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


@router.get("/stats", response_model=StatsOut)
async def admin_stats() -> StatsOut:
    base = _chats_dir()
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    total_24h = 0
    active_users: set[str] = set()
    latencies: list[float] = []
    moderation_blocked = 0
    feedback_up = 0
    feedback_down = 0

    if not base.exists():
        return StatsOut(
            total_messages_24h=0,
            active_users=0,
            avg_latency_ms=0.0,
            moderation_block_rate=0.0,
            feedback_up_ratio=0.0,
        )

    for chat_dir in base.iterdir():
        if not chat_dir.is_dir():
            continue
        for msg in _iter_messages(chat_dir):
            created = msg.get("created_at")
            try:
                ts = datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None
            except Exception:
                ts = None
            if ts is None or ts < since:
                continue
            total_24h += 1
            owner = msg.get("owner_external_id") or ""
            if owner:
                active_users.add(str(owner))
            if msg.get("latency_ms") is not None:
                try:
                    latencies.append(float(msg["latency_ms"]))
                except Exception:
                    pass
            if msg.get("moderation_blocked"):
                moderation_blocked += 1
            fb = msg.get("feedback")
            if fb == 1:
                feedback_up += 1
            elif fb == -1:
                feedback_down += 1

    total_fb = feedback_up + feedback_down
    return StatsOut(
        total_messages_24h=total_24h,
        active_users=len(active_users),
        avg_latency_ms=(sum(latencies) / len(latencies)) if latencies else 0.0,
        moderation_block_rate=(moderation_blocked / total_24h) if total_24h else 0.0,
        feedback_up_ratio=(feedback_up / total_fb) if total_fb else 0.0,
    )


@router.get("/users", response_model=list[UserOut])
async def admin_users(limit: int = 50) -> list[UserOut]:
    base = _chats_dir()
    if not base.exists():
        return []

    out: list[UserOut] = []
    for chat_dir in base.iterdir():
        if not chat_dir.is_dir():
            continue
        meta_path = chat_dir / "chat.json"
        if not meta_path.exists():
            meta_path = chat_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        count = 0
        last_seen = None
        for msg in _iter_messages(chat_dir):
            count += 1
            ts = msg.get("created_at")
            if ts and (last_seen is None or ts > last_seen):
                last_seen = ts

        out.append(
            UserOut(
                owner_external_id=str(meta.get("owner_external_id", "")),
                interface=meta.get("interface", "telegram"),
                message_count=count,
                last_seen=last_seen,
            )
        )
    out.sort(key=lambda u: u.message_count, reverse=True)
    return out[: max(1, min(limit, 200))]

@router.post("/broadcast", response_model=BroadcastResult)
async def admin_broadcast(body: BroadcastBody) -> BroadcastResult:
    sent = 0
    failed = 0
    for meta in _iter_chats():
        if body.interface_filter and meta.get("interface") != body.interface_filter:
            continue
        try:
            tg_id = int(str(meta.get("owner_external_id", "")))
        except (TypeError, ValueError):
            failed += 1
            continue
        try:
            await notify_user(tg_id, body.message)
            sent += 1
        except Exception as exc:
            logger.warning("broadcast_failed chat=%s err=%s", meta.get("id"), exc)
            failed += 1
    return BroadcastResult(sent=sent, failed=failed)