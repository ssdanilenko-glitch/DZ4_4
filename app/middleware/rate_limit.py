import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceeded

settings = get_settings()

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        redis_client = request.app.state.redis
        if redis_client is None:
            return await call_next(request)

        user_id = request.headers.get("X-User-Id")
        if not user_id:
            forwarded = request.headers.get("X-Forwarded-For")
            user_id = forwarded.split(",")[0].strip() if forwarded else request.client.host

        key = f"rate_limit:{user_id}"
        current_minute = int(time.time() / 60)
        key_minute = f"{key}:{current_minute}"

        try:
            count = await redis_client.incr(key_minute)
            if count == 1:
                await redis_client.expire(key_minute, 60)

            limit = settings.rate_limit_per_min
            if count > limit:
                reset_after = 60 - (time.time() % 60)
                raise RateLimitExceeded(limit=limit, reset_after=int(reset_after))
        except Exception:
            pass

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_min)
        response.headers["X-RateLimit-Remaining"] = str(max(0, settings.rate_limit_per_min - count))
        return response