import pytest
from app.observability.pii import redact_pii, prompt_hash


def test_redact_pii_email():
    """Проверка замены email."""
    text = "My email is test@example.com"
    result = redact_pii(text)
    assert "[EMAIL]" in result
    assert "test@example.com" not in result


def test_redact_pii_phone():
    """Проверка замены российского номера телефона (разные форматы)."""
    texts = [
        "+7 (999) 123-45-67",
        "+7 999 123 45 67",
        "8 (999) 123-45-67",
        "89991234567",
        "+7 999 123-45-67",
    ]
    for original in texts:
        result = redact_pii(original)
        assert "[PHONE_RU]" in result
        assert original not in result


def test_redact_pii_card():
    """Проверка замены номера банковской карты."""
    text = "Card: 4111 1111 1111 1111"
    result = redact_pii(text)
    assert "[CARD]" in result
    assert "4111 1111 1111 1111" not in result


def test_redact_pii_inn():
    """Проверка замены ИНН (10 или 12 цифр)."""
    texts = ["1234567890", "123456789012"]
    for inn in texts:
        result = redact_pii(f"INN {inn}")
        assert "[INN]" in result
        assert inn not in result


def test_redact_pii_passport():
    """Проверка замены серии и номера паспорта."""
    text = "Passport 12 34 567890"
    result = redact_pii(text)
    assert "[PASSPORT]" in result
    assert "12 34 567890" not in result


def test_redact_pii_combined():
    """Проверка замены всех типов PII в одном тексте."""
    text = (
        "Мой email ivan@mail.ru, тел +7 (999) 123-45-67, "
        "карта 4111 1111 1111 1111, ИНН 1234567890, паспорт 12 34 567890"
    )
    result = redact_pii(text)
    # Проверяем наличие всех плейсхолдеров
    assert "[EMAIL]" in result
    assert "[PHONE_RU]" in result
    assert "[CARD]" in result
    assert "[INN]" in result
    assert "[PASSPORT]" in result
    # Проверяем, что исходных данных нет
    assert "ivan@mail.ru" not in result
    assert "+7 (999) 123-45-67" not in result
    assert "4111 1111 1111 1111" not in result
    assert "1234567890" not in result
    assert "12 34 567890" not in result


def test_redact_pii_no_pii():
    """Текст без PII должен оставаться неизменным."""
    text = "This is a normal text without any PII data."
    result = redact_pii(text)
    assert result == text


def test_redact_pii_partial():
    """Проверка, что не-PII части текста сохраняются."""
    text = "My email is test@example.com and my phone is +7 999 123 45 67"
    result = redact_pii(text)
    # Сохранились ли обычные слова?
    assert "My email is" in result
    assert "and my phone is" in result
    # Плейсхолдеры на месте
    assert "[EMAIL]" in result
    assert "[PHONE_RU]" in result


def test_prompt_hash():
    """Проверка вычисления хеша промпта."""
    text = "some prompt"
    h = prompt_hash(text)
    assert h.startswith("sha256:")
    # Хеш должен быть длиной 7 ("sha256:") + 16 hex-символов = 23
    assert len(h) == 7 + 16
    # Одинаковый текст → одинаковый хеш
    assert prompt_hash(text) == h
    # Разный текст → разный хеш
    assert prompt_hash("different") != h