from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Темы из домена дипломного проекта (SaaS-техподдержка)
TOPICS: list[tuple[str, str]] = [
    ("Биллинг", "billing"),
    ("Установка", "install"),
    ("Ошибки API", "api-errors"),
    ("Интеграция", "integration"),
]


def topics_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, slug in TOPICS:
        builder.button(text=label, callback_data=f"topic:{slug}")
    builder.button(text="Отмена", callback_data="topic:cancel")
    builder.adjust(2)
    return builder.as_markup()