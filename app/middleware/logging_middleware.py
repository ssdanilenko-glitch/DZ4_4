from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import uuid
from structlog.contextvars import bind_contextvars, clear_contextvars
import time
import structlog

logger = structlog.get_logger()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        bind_contextvars(
            request_id=request_id,
            user_id=None,
            path=request.url.path,
            method=request.method,
        )
        start_time = time.time()
        try:
            response = await call_next(request)
            process_time = (time.time() - start_time) * 1000
            response.headers["x-request-id"] = request_id
            logger.info(
                "http_request_completed",
                status_code=response.status_code,
                duration_ms=round(process_time, 2),
            )
            return response
        except Exception:
            logger.exception("http_request_failed")
            raise
        finally:
            clear_contextvars()