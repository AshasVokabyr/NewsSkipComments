# main.py
from config import (
    BOT_TOKEN, MISTRAL_API_KEY, ADMINS, TECHCRUNCH_URL,
    COLLECTION_TIME, POSTING_TIME, CHANNEL_ID
)
from db import Database
from handlers import is_admin, get_admin_keyboard

import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from mistralai import Mistral
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Optional, Dict, List
from datetime import datetime
import pytz
import asyncio

# Инициализация логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация клиента Mistral
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Глобальные переменные
bot_enabled = True

# Инициализация базы данных
db = Database()

async def fetch_article_content(url: str) -> Optional[str]:
    """Загружает содержимое статьи"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                logger.warning(f"Статус ответа {response.status} для URL: {url}")
                return None
    except Exception as e:
        logger.error(f"Ошибка при получении статьи {url}: {str(e)}")
        return None

async def is_question(text: str) -> bool:
    """Определяет, является ли текст вопросом с помощью Mistral"""
    try:
        prompt = (
            "Определи, является ли следующий текст вопросом. "
            "Ответь только JSON с ключами: is_question (булево), "
            "confidence (уверенность 0-1).\n\nТекст: " + text
        )
        
        response = mistral_client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get('is_question', False) and result.get('confidence', 0) >= 0.7
        
    except Exception as e:
        logger.error(f"Ошибка при определении вопроса: {e}")
        return False

async def generate_answer(question: str, article_contents: List[Dict]) -> Optional[Dict]:
    """Генерирует ответ на вопрос на основе контента статей"""
    try:
        articles_text = ""
        for i, article in enumerate(article_contents, 1):
            articles_text += f"\n\n--- Статья {i} ---\n{article['content']}"
        
        prompt = (
            f"Сгенерируй краткий ответ (не более 300 слов) на вопрос на основе предоставленных статей.\n\n"
            f"Вопрос: {question}\n\n"
            f"Статьи:{articles_text}\n\n"
            "Ответ должен быть четким, информативным и содержать номер использованной статьи."
        )
        
        response = mistral_client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        
        answer = response.choices[0].message.content
        if not answer:
            return None
            
        return {
            "text": answer if len(answer) <= 2000 else answer[:2000] + "..."
        }
        
    except Exception as e:
        logger.error(f"Ошибка при генерации ответа: {e}")
        return None

async def parse_article_content(html_content: str) -> Optional[str]:
    """Парсит текст статьи из HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        for element in soup(['script', 'style', 'nav', 'footer', 'iframe', 'img']):
            element.decompose()
        
        text = soup.get_text(separator='\n', strip=True)
        text = '\n'.join(line for line in text.splitlines() if line.strip())
        return text[:5000]
    except Exception as e:
        logger.error(f"Ошибка при парсинге статьи: {e}")
        return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer(
            "🤖 Бот для ответов на вопросы в комментариях\n\n"
            "Используйте кнопки ниже для управления ботом",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer("Доступ запрещен")

@dp.message(F.text == "🔄 Статус", lambda message: is_admin(message.from_user.id))
async def bot_status(message: types.Message):
    await message.answer(
        f"Статус: {'🟢 Включен' if bot_enabled else '🔴 Выключен'}\n"
        f"Время: {datetime.now(pytz.timezone('Europe/Moscow')).strftime('%d.%m.%Y %H:%M:%S')} МСК",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "✅ Вкл. бота", lambda message: is_admin(message.from_user.id))
async def enable_bot(message: types.Message):
    global bot_enabled
    bot_enabled = True
    await message.answer("🟢 Бот включен", reply_markup=get_admin_keyboard())
    logger.info(f"Бот включен администратором {message.from_user.id}")

@dp.message(F.text == "⛔ Выкл. бота", lambda message: is_admin(message.from_user.id))
async def disable_bot(message: types.Message):
    global bot_enabled
    bot_enabled = False
    await message.answer("🔴 Бот выключен", reply_markup=get_admin_keyboard())
    logger.info(f"Бот выключен администратором {message.from_user.id}")

@dp.message(F.chat.type.in_({'group', 'supergroup'}))
async def handle_group_message(message: types.Message):
    """Обработчик сообщений в группе (чате комментариев)"""
    if not bot_enabled:
        return
    
    try:
        # Если это ответ на сообщение - добавляем задержку и проверяем пост
        parent_id = None
        if message.reply_to_message:
            logger.info(f"Начат процесс сохранения комментария к сообщению {message.reply_to_message.message_id}")
            
            # Задержка 8 секунд для ожидания поста
            logger.info("Ожидание 8 секунд для синхронизации с ботом постов...")
            await asyncio.sleep(8)
            logger.info("Задержка завершена, проверка наличия поста в БД...")
            
            # Проверяем существование поста
            parent_message = await db.get_message_by_telegram_id(message.reply_to_message.message_id)
            if not parent_message:
                logger.warning(f"Родительское сообщение {message.reply_to_message.message_id} не найдено в БД")
                return
                
            parent_id = parent_message['id']
            logger.info(f"Найден родительский пост с ID: {parent_id}")

        # Сохраняем комментарий
        await db.insert_message(
            telegram_id=message.message_id,
            message_text=message.text,
            user_id=message.from_user.id,
            username=message.from_user.username,
            parent_id=parent_id,
        )
        logger.info(f"Комментарий {message.message_id} сохранён в БД")

        # Дальнейшая обработка вопроса...
        if not message.reply_to_message or not await is_question(message.text):
            return
            
        logger.info(f"Обнаружен вопрос в сообщении {message.message_id}")
        
        # Получаем данные родительского сообщения
        parent_message = await db.get_message_by_telegram_id(message.reply_to_message.message_id)
        if not parent_message or not parent_message.get('url'):
            return
            
        article_urls = parent_message['url']
        if not isinstance(article_urls, list):
            article_urls = [article_urls]
        
        # Собираем контент всех статей
        articles_data = []
        for url in article_urls[:3]:
            content = await fetch_article_content(url)
            if content:
                parsed = await parse_article_content(content)
                if parsed:
                    articles_data.append({
                        "url": url,
                        "content": parsed
                    })
        
        if not articles_data:
            return
            
        # Генерируем ответ
        answer_result = await generate_answer(message.text, articles_data)
        if not answer_result:
            return
        
        # Отправляем ответ
        await message.reply(answer_result["text"])
        
        # Сохраняем ответ в базу
        await db.insert_message(
            telegram_id=f"answer_{message.message_id}",
            message_text=answer_result["text"],
            user_id=bot.id,
            username=bot.username,
            parent_id=message.message_id,
        )
        
        logger.info(f"Ответ отправлен для сообщения {message.message_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения {message.message_id}: {str(e)}")

async def on_startup():
    """Функция, выполняемая при запуске бота"""
    for admin_id in ADMINS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text="🤖 Бот запущен и готов к работе!",
                reply_markup=get_admin_keyboard()
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")

async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск бота...")
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())