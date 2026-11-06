# app/admin/deps.py
from fastapi import Header, HTTPException

from app.core.config import get_settings


async def require_admin(x_admin_token: str = Header(..., alias="X-Admin-Token")):
    settings = get_settings()
    expected = getattr(settings, "ADMIN_TOKEN", None)
    if not expected:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")