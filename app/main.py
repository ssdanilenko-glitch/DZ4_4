import secrets
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from dotenv import load_dotenv
load_dotenv()
from app.chat.routes import router as chat_router
from app.admin.routes import router as admin_router

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None

from app.core.config import get_settings
from app.core.exceptions import (
    LLMAuthError,
    LLMContentFilterError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    RateLimitExceeded,  # ИСПРАВЛЕНО: добавлен импорт
)
from app.routers import chat, health, models

# --- Новые импорты для observability ---
import structlog
from app.observability.tracing import setup_tracing # Импортируем функцию
from app.observability.logging import setup_logging
from app.observability.pii import redact_pii, prompt_hash # Импортируем PII функции
from structlog.contextvars import bind_contextvars, clear_contextvars
from app.chat.feedback import router as feedback_router
# ---------------------------------------
from app.middleware.rate_limit import RateLimitMiddleware
from app.db import init_db

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Настройка structlog (JSON-логи)
    # Если в settings нет log_level, можно передать "INFO"
    setup_logging(level=getattr(settings, "log_level", "INFO"))

    # 2. Инициализация трассировки Phoenix ДО создания клиента OpenAI
    setup_tracing(project_name="diploma-fastapi")
    # --- Б4.4: инициализация БД ---
    try:
        await init_db()
        logger.info("db_initialized")
    except Exception as e:
        logger.error("db_init_failed", error=str(e))
    # 3. Инициализация OpenAI клиента
    app.state.llm = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout=settings.llm.request_timeout,
        max_retries=settings.llm.max_retries,
    )

    # 4. Инициализация Redis (опционально)
    app.state.redis = None
    if Redis is not None:
        try:
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
            await redis_client.ping()
            app.state.redis = redis_client
            logger.info("redis_connected")
        except Exception as e:
            logger.warning("redis_unavailable", error=str(e))

    app.state.canary = secrets.token_hex(4)
    logger.info("canary_generated", canary=app.state.canary)


    yield

    # Закрытие соединений
    try:
        await app.state.llm.close()
    except Exception:
        pass
    if app.state.redis is not None:
        try:
            await app.state.redis.close()
        except Exception:
            pass


# Создание приложения с lifespan
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="FastAPI-сервис для LLM",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-LLM-Cost-USD"],

)

# ---------- ДОБАВЛЯЕМ RATE LIMITING MIDDLEWARE (после CORS) ----------
# ИСПРАВЛЕНО: middleware добавляется здесь, а не в lifespan
app.add_middleware(RateLimitMiddleware)   # Предполагается, что middleware переписан
# -------------------------------------------------------------------

# Middleware для observability (structlog + request_id)
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    # Получаем или генерируем request_id (берём первые 12 символов UUID)
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    # Привязываем контекстные переменные для structlog
    bind_contextvars(
        request_id=request_id,
        user_id=None,  # можно заполнить из аутентификации
        path=request.url.path,
        method=request.method,
    )
    request.state.request_id = request_id
    request.state.llm_cost = 0.0
    request.state.llm_tokens = 0

    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Логируем исключение с уже привязанным контекстом
        logger.exception("unhandled_exception")
        clear_contextvars()
        raise

    duration_ms = (time.perf_counter() - t0) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-LLM-Cost-USD"] = f"{request.state.llm_cost:.6f}"

    logger.info(
        "http_request_completed",
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    clear_contextvars()
    return response


# Маппинг исключений LLM на HTTP статусы и коды ошибок
_STATUS_MAP: list[tuple[type[LLMError], int, str]] = [
    (LLMRateLimitError, 429, "llm_rate_limit"),
    (LLMAuthError, 502, "llm_auth"),
    (LLMTimeoutError, 504, "llm_timeout"),
    (LLMContentFilterError, 400, "content_filter"),
    (LLMError, 502, "llm_error"),
]


@app.exception_handler(LLMError)
async def handle_llm_error(request: Request, exc: LLMError):
    for cls, status, code in _STATUS_MAP:
        if isinstance(exc, cls):
            return JSONResponse(
                status_code=status,
                content={"error": {"code": code, "message": str(exc)}},
                headers={"X-Request-ID": getattr(request.state, "request_id", "")},
            )
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "llm_error", "message": str(exc)}},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "fields": errors}},
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )

@app.exception_handler(RateLimitExceeded)
async def handle_rate_limit(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limit_exceeded",
                "message": f"Too many requests. Limit: {exc.limit} per minute. Try again in {int(exc.reset_after)} seconds.",
            }
        },
        headers={
            "Retry-After": str(int(exc.reset_after)),
            "X-RateLimit-Limit": str(exc.limit),
        },
    )

# Подключение роутеров
app.include_router(chat.router)
app.include_router(models.router)
app.include_router(health.router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(feedback_router)


# Корневой эндпоинт
@app.get("/")
async def root():
    return {"message": "LLM service is running"}