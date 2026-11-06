import re
from dataclasses import dataclass
from typing import Final

# Максимальная длина текста (символов)
MAX_INPUT_CHARS: Final[int] = 4000

# Допустимая доля непечатаемых символов (кроме \n, \r, \t)
NON_PRINTABLE_RATIO_LIMIT: Final[float] = 0.10

# Паттерны для поиска инъекций (регистронезависимые)
INJECTION_PATTERNS: Final[list[re.Pattern]] = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(the\s+)?(system|previous|above)\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+(a|an|the|dan|do anything now)\b", re.IGNORECASE),
    re.compile(r"\bforget\s+(everything|all|previous)\b", re.IGNORECASE),
    re.compile(r"\b(jailbroken|developer mode|godmode)\b", re.IGNORECASE),
    # Дополнительные распространённые паттерны
    re.compile(r"\b(new\s+instruction|new\s+rule|new\s+command)\b", re.IGNORECASE),
    re.compile(r"\b(system\s+prompt|system\s+message|system\s+instruction)\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class ValidationResult:
    """Результат валидации входного текста."""
    ok: bool
    reason: str | None = None
    rule: str | None = None  # имя сработавшего правила


def validate_input(text: str) -> ValidationResult:
    """
    Проверяет входной текст на соответствие политике безопасности.

    Правила:
      - Длина текста <= MAX_INPUT_CHARS
      - Доля непечатаемых символов (кроме \\n, \\r, \\t) <= NON_PRINTABLE_RATIO_LIMIT
      - Отсутствие паттернов инъекций из INJECTION_PATTERNS

    Возвращает ValidationResult с флагом ok и пояснением.
    """
    # 1. Проверка длины
    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(
            ok=False,
            reason=f"Input too long: {len(text)} > {MAX_INPUT_CHARS}",
            rule="length"
        )

    # 2. Проверка доли непечатаемых символов
    # Считаем непечатаемыми все, кроме isprintable() и разрешённых управляющих
    non_printable_count = sum(1 for c in text if not c.isprintable() and c not in "\n\r\t")
    if len(text) > 0:
        ratio = non_printable_count / len(text)
    else:
        ratio = 0.0

    if ratio > NON_PRINTABLE_RATIO_LIMIT:
        return ValidationResult(
            ok=False,
            reason=f"High non-printable ratio: {ratio:.2%} > {NON_PRINTABLE_RATIO_LIMIT:.0%}",
            rule="encoding"
        )

    # 3. Проверка на паттерны инъекций
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return ValidationResult(
                ok=False,
                reason=f"Matched injection pattern: {pattern.pattern}",
                rule="injection"
            )

    # Все проверки пройдены
    return ValidationResult(ok=True)