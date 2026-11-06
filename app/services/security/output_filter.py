import re
from typing import Final

# Регулярные выражения для PII (совпадают с redact_pii из app/observability/pii.py)
EMAIL_RE: Final[re.Pattern] = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
PHONE_RU_RE: Final[re.Pattern] = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
)
PASSPORT_RU_RE: Final[re.Pattern] = re.compile(
    r"\b\d{4}\s?\d{6}\b"
)


def filter_output(answer: str, system_prompt: str, canary: str) -> str:
    """
    Фильтрует ответ LLM:
      - Проверяет наличие канарейки и фрагментов системного промпта.
      - Маскирует PII.

    Аргументы:
      answer: сырой ответ от LLM.
      system_prompt: полный системный промпт, который был отправлен модели.
      canary: секретная метка, добавленная в системный промпт.

    Возвращает:
      Отфильтрованный ответ с заменёнными PII.

    Исключения:
      ValueError – если обнаружена утечка системного промпта (канарейка или начало промпта).
    """
    # 1. Проверка канарейки
    if canary and canary in answer:
        raise ValueError("system_prompt leakage: canary detected")

    # 2. Проверка фрагмента системного промпта (первые 80 слов)
    #    Берём первые 80 слов из системного промпта, чтобы не сравнивать весь длинный текст.
    words = system_prompt.split()
    prefix = " ".join(words[:80]) if words else ""
    if prefix and prefix.lower() in " ".join(answer.split()).lower():
        raise ValueError("system_prompt leakage: prefix detected")

    # 3. Маскирование PII
    masked = EMAIL_RE.sub("[EMAIL]", answer)
    masked = PHONE_RU_RE.sub("[PHONE_RU]", masked)
    masked = PASSPORT_RU_RE.sub("[PASSPORT]", masked)

    return masked