from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def feedback_keyboard(message_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="👍", callback_data=f"fb:up:{message_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"fb:down:{message_id}"),
        ]]
    )