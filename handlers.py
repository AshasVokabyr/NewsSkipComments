# handlers.py
from aiogram import Bot
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from typing import Optional, Dict
import re

from config import ADMINS
from db import Database

db = Database()

def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMINS

def get_admin_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔄 Статус"))
    builder.row(
        types.KeyboardButton(text="✅ Вкл. бота"),
        types.KeyboardButton(text="⛔ Выкл. бота")
    )
    return builder.as_markup(resize_keyboard=True)

def get_approval_keyboard(message_id: int):
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text=f"✅ Одобрить {message_id}"),
        types.KeyboardButton(text=f"❌ Отклонить {message_id}")
    )
    builder.row(
        types.KeyboardButton(text=f"🔄 Перегенерировать {message_id}"),
        types.KeyboardButton(text=f"✏️ Редактировать {message_id}")
    )
    return builder.as_markup(resize_keyboard=True)

async def extract_message_id(text: str) -> Optional[int]:
    match = re.match(r"^(✅ Одобрить|❌ Отклонить|🔄 Перегенерировать|✏️ Редактировать) (\d+)$", text)
    return int(match.group(2)) if match else None

async def notify_admins(bot: Bot, text: str, reply_markup=None):
    """Отправляет уведомление всем администраторам"""
    for admin_id in ADMINS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=None,  # Отключаем разметку полностью
                disable_web_page_preview=True,
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление админу {admin_id}: {e}")