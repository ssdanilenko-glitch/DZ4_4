import json
import logging

import httpx

logger = logging.getLogger(__name__)


def _safe_body(resp: httpx.Response) -> dict:
    """Пытается достать JSON из ответа, не падая на streaming-ответах."""
    try:
        return resp.json()
    except Exception:
        pass
    try:
        raw = resp.text  # может бросить ResponseNotRead
    except Exception:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _safe_raw(resp: httpx.Response) -> str:
    try:
        return resp.text
    except Exception:
        return ""


def humanize_backend_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        raw = _safe_raw(exc.response)
        body = _safe_body(exc.response)
        logger.warning("humanize_backend_error status=%s raw=%r", status, raw[:300])

        detail = body.get("detail") if isinstance(body, dict) else None

        code = None
        cats: list[str] = []
        if isinstance(detail, dict):
            code = detail.get("code")
            cats = detail.get("categories") or []
        elif isinstance(detail, str):
            code = detail
        if not code and isinstance(body, dict):
            code = body.get("code")

        if code == "moderation_blocked" or '"moderation_blocked"' in raw:
            cat_str = ", ".join(cats) if cats else "—"
            return f"🚫 Сообщение заблокировано модерацией.\nКатегории: {cat_str}"

        if status == 404:
            return "❌ Чат не найден."
        if status == 415:
            return "❌ Неподдерживаемый формат файла."
        if status == 400:
            msg = detail if isinstance(detail, str) else (detail or {}).get("message", "Некорректный запрос")
            return f"❌ {msg}"
        if 500 <= status < 600:
            return "⚠️ Backend временно недоступен. Попробуйте позже."
        return f"⚠️ Ошибка backend: HTTP {status}"

    if isinstance(exc, httpx.TimeoutException):
        return "⏱ Backend не ответил вовремя. Попробуйте позже."
    if isinstance(exc, httpx.RequestError):
        return "🔌 Не удалось связаться с backend. Проверьте соединение."

    if type(exc).__name__ == "BackendError":
        return f"⚠️ {exc}"

    return "⚠️ Произошла ошибка. Попробуйте позже."