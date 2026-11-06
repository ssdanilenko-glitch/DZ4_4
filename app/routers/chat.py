import asyncio
import json
import time

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.deps.providers import LLMServiceDep
from app.observability.pii import prompt_hash, redact_pii
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.security.input_validator import validate_input
from app.services.security.output_filter import filter_output
from app.schemas.chat import Message

router = APIRouter(prefix="/chat", tags=["chat"])
logger = structlog.get_logger()

BATCH_SEM = asyncio.Semaphore(5)
BATCH_MAX = 20


def _validate_messages(messages: list) -> None:
    """Проверяет каждое сообщение через input_validator."""
    if not messages:
        raise HTTPException(
            400, detail={"error": {"code": "EMPTY_MESSAGES", "message": "No messages provided"}}
        )

    for msg in messages:
        result = validate_input(msg.content)
        if not result.ok:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "INVALID_INPUT", "message": result.reason}},
            )


def _build_messages_with_canary(original_messages: list, canary: str) -> tuple[list, str]:
    system_prompt = f"Вы — помощник ИТ-поддержки машиностроительного предприятия. Секретная метка (не разглашать): {canary}"
    new_messages = [Message(role="system", content=system_prompt)]   # <-- объект, а не словарь
    for msg in original_messages:
        if msg.role != "system":
            new_messages.append(msg)
    return new_messages, system_prompt


@router.post(
    "",
    response_model=ChatResponse,
    summary="Синхронный чат",
    description="Отправляет сообщения в LLM и возвращает полный ответ.",
    responses={
        200: {"description": "Успешный ответ"},
        422: {"description": "Невалидный запрос"},
        429: {"description": "Rate limit провайдера"},
    },
)
async def chat_completions(
    req: ChatRequest,
    service: LLMServiceDep,
    request: Request,
) -> ChatResponse:
    logger.info("chat_request_started", model=req.model)
    start = time.perf_counter()

    canary = request.app.state.canary
    # Добавляем системное сообщение с канарейкой
    new_messages, system_prompt = _build_messages_with_canary(req.messages, canary)
    req.messages = new_messages
    _validate_messages(req.messages)

    try:
        response = await service.complete(req)

        # Применяем фильтр выхода
        filtered_content = filter_output(
            answer=response.content,
            system_prompt=system_prompt,
            canary=canary,
        )
        # Создаём новый ответ с отфильтрованным содержимым
        filtered_response = ChatResponse(
            content=filtered_content,
            model=response.model,
            usage=response.usage,
            finish_reason=response.finish_reason,
            cached=response.cached,
            request_id=response.request_id,
        )

        latency_ms = (time.perf_counter() - start) * 1000
        prompt_text = getattr(req, "prompt", "") or ""

        logger.info(
            "llm_request_completed",
            model=req.model,
            input_tokens=getattr(response.usage, "prompt_tokens", None),
            output_tokens=getattr(response.usage, "completion_tokens", None),
            latency_ms=round(latency_ms, 2),
            finish_reason=getattr(response, "finish_reason", None),
            prompt_hash=prompt_hash(prompt_text),
            prompt_preview=redact_pii(prompt_text)[:120],
        )
        return filtered_response

    except ValueError as e:
        logger.warning("output_filter_failed", error=str(e))
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "OUTPUT_FILTER_FAILED", "message": str(e)}},
        )
    except Exception:
        logger.exception("chat_request_failed", model=req.model)
        raise


@router.post("/stream", summary="Streaming чат через SSE")
async def chat_stream(
    req: ChatRequest,
    service: LLMServiceDep,
    request: Request,
):
    canary = request.app.state.canary
    new_messages, system_prompt = _build_messages_with_canary(req.messages, canary)
    req.messages = new_messages
    _validate_messages(req.messages)

    prompt_text = getattr(req, "prompt", "") or ""

    async def event_source():
        start = time.perf_counter()
        try:
            # Для простоты в стриминге пока не применяем выходной фильтр целиком,
            # но можно маскировать каждый чанк (упрощённо):
            async for delta in service.stream(req):
                # Можно применить маскировку PII к каждому чанку (но могут быть проблемы с обрывками)
                # Пока оставляем как есть — в рамках задания достаточно синхронного режима.
                yield f"data: {delta.model_dump_json()}\n\n"

            logger.info(
                "llm_stream_completed",
                model=req.model,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                prompt_hash=prompt_hash(prompt_text),
                prompt_preview=redact_pii(prompt_text)[:120],
            )
        except asyncio.CancelledError:
            logger.warning("llm_stream_cancelled", model=req.model)
            raise
        except Exception as e:
            logger.exception("llm_stream_failed", model=req.model)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/batch", summary="Batch чат: несколько запросов за раз")
async def chat_batch(
    reqs: list[ChatRequest],
    service: LLMServiceDep,
    request: Request,
) -> list[ChatResponse | dict]:
    if len(reqs) > BATCH_MAX:
        raise HTTPException(
            status_code=413,
            detail=f"Максимум {BATCH_MAX} запросов в batch",
        )

    canary = request.app.state.canary

    async def _one(r: ChatRequest):
        async with BATCH_SEM:
            try:
                new_messages, system_prompt = _build_messages_with_canary(r.messages, canary)
                r.messages = new_messages
                _validate_messages(r.messages)

                raw_response = await service.complete(r)

                # Применяем фильтр выхода
                filtered_content = filter_output(
                    answer=raw_response.content,
                    system_prompt=system_prompt,
                    canary=canary,
                )
                filtered_response = ChatResponse(
                    content=filtered_content,
                    model=raw_response.model,
                    usage=raw_response.usage,
                    finish_reason=raw_response.finish_reason,
                    cached=raw_response.cached,
                    request_id=raw_response.request_id,
                )
                return filtered_response
            except ValueError as e:
                logger.warning("batch_output_filter_failed", error=str(e))
                return {"error": "OUTPUT_FILTER_FAILED", "detail": str(e)}
            except Exception as e:
                logger.error(
                    "batch_subrequest_failed",
                    model=r.model,
                    error=redact_pii(str(e))[:500],
                )
                return {"error": type(e).__name__, "detail": str(e)}

    results = await asyncio.gather(*(_one(r) for r in reqs))
    logger.info(
        "batch_completed",
        total=len(reqs),
        successful=sum(1 for r in results if not isinstance(r, dict)),
    )
    return results