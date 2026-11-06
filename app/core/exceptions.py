class LLMError(Exception):
    """Базовое доменное исключение слоя LLM."""


class LLMRateLimitError(LLMError):
    """Провайдер вернул rate limit."""


class LLMAuthError(LLMError):
    """Невалидный ключ или 401/403 от провайдера."""


class LLMTimeoutError(LLMError):
    """LLM не ответил вовремя."""

class RateLimitExceeded(Exception):
    def __init__(self, limit: int, reset_after: int):
        self.limit = limit
        self.reset_after = reset_after
        super().__init__(f"Rate limit exceeded. Limit: {limit} per minute. Reset in {reset_after}s")


class LLMContentFilterError(LLMError):
    """Контент заблокирован модерацией."""
