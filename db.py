# db.py
from config import SUPABASE_URL, SUPABASE_KEY
from typing import Optional, Dict, List, Union
from supabase import create_client, Client
from supabase.client import ClientOptions
from supabase import PostgrestAPIError
import json


class Database:
    """Класс для работы с сообщениями Telegram-бота в Supabase."""
    
    def __init__(self):
        """Инициализация подключения к Supabase."""
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not found in config")
            
        self.client: Client = create_client(
            SUPABASE_URL,
            SUPABASE_KEY,
            options=ClientOptions(postgrest_client_timeout=10)
        )
        self.table_name = "messages"
    
    async def insert_message(
        self,
        telegram_id: int,
        message_text: str,
        url: Optional[Union[str, List[str]]] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        parent_id: Optional[int] = None,
        is_post: bool = False,
        chat_id: Optional[int] = None
    ) -> Optional[Dict]:
        """Добавляет новое сообщение в базу данных."""
        try:
            message_data = {
                "telegram_id": telegram_id,
                "message_text": message_text,
                "user_id": user_id,
                "is_post": is_post,
                "username": username,
                "parent_id": parent_id,
            }
            
            if url:
                if isinstance(url, list):
                    message_data["url"] = json.dumps(url)
                elif isinstance(url, str):
                    try:
                        json.loads(url)
                        message_data["url"] = url
                    except json.JSONDecodeError:
                        message_data["url"] = json.dumps([url])
            
            message_data = {k: v for k, v in message_data.items() if v is not None}
            
            response = (
                self.client
                .table(self.table_name)
                .insert(message_data)
                .execute()
            )
            
            return response.data[0] if response.data else None
            
        except PostgrestAPIError as e:
            print(f"Database error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
    
    async def get_message_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Получает сообщение по его telegram_id."""
        try:
            response = (
                self.client
                .table(self.table_name)
                .select("*")
                .eq("telegram_id", telegram_id)
                .execute()
            )
            if response.data:
                message = response.data[0]
                if message.get('url'):
                    try:
                        message['url'] = json.loads(message['url'])
                    except json.JSONDecodeError:
                        message['url'] = [message['url']]
                return message
            return None
        except PostgrestAPIError as e:
            print(f"Database error: {e}")
            return None
    
    async def get_replies_by_parent_id(self, parent_id: int) -> List[Dict]:
        """Получает все ответы на указанное сообщение."""
        try:
            response = (
                self.client
                .table(self.table_name)
                .select("*")
                .eq("parent_id", parent_id)
                .execute()
            )
            return response.data if response.data else []
        except PostgrestAPIError as e:
            print(f"Database error: {e}")
            return []
    
    async def update_message(self, id: int, fields: Dict) -> Optional[Dict]:
        """Обновляет данные сообщения."""
        try:
            # Удаляем None значения
            fields = {k: v for k, v in fields.items() if v is not None}
            
            if not fields:
                raise ValueError("No fields to update provided")
                
            response = (
                self.client
                .table(self.table_name)
                .update(fields)
                .eq("id", id)
                .execute()
            )
            return response.data[0] if response.data else None
        except PostgrestAPIError as e:
            print(f"Database error: {e}")
            return None
        except ValueError as e:
            print(f"Validation error: {e}")
            return None