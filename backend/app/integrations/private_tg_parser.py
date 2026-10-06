from telethon.sync import TelegramClient
from dotenv import find_dotenv, load_dotenv
import os
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional, Union

from telethon import TelegramClient
from telethon.tl.custom.message import Message
from telethon.errors import FloodWaitError

load_dotenv()

class PrivateTgParser:
    def __init__(self, session_name: str = "tg_parser", *, api_id=None, api_hash=None, phone=None):
        self.api_id = api_id or os.getenv('TG_API_ID')
        self.api_hash = api_hash or os.getenv('TG_API_HASH')
        self.phone = phone or os.getenv('TG_PHONE_NUM')
        self.session_name = session_name
        self.client = None

    async def __aenter__(self):
        """Позволяет использовать класс через async with."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self, phone: Optional[str] = None):
        """Подключение к Telegram и авторизация."""
        if self.client and self.client.is_connected():
            return
        if not self.api_id or not self.api_hash:
            raise RuntimeError("Не заданы TG_API_ID и TG_API_HASH (env или аргументы конструктора).")
        self.client = TelegramClient(self.session_name, int(self.api_id), self.api_hash)
        await self.client.start(phone=phone or self.phone)

    async def disconnect(self):
        """Отключение от Telegram."""
        if self.client and self.client.is_connected():
            await self.client.disconnect()

    @staticmethod
    def _to_utc(dt: datetime) -> datetime:
        """Приводит datetime к UTC (Telegram хранит даты в UTC)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    async def get_channel_messages(
            self,
            channel: Union[str, int],
            date_from: datetime,
            date_to: datetime,
            limit_per_request: int = 100,
            max_messages: Optional[int] = None,
    ) -> List[Message]:
        """
        Получить сообщения из одного канала за промежуток [date_from, date_to].

        :param channel: username (@name), ссылка (t.me/name) или ID канала
        :param date_from: начало промежутка
        :param date_to: конец промежутка
        :param limit_per_request: размер пакета запроса (макс. 100)
        :param max_messages: ограничение на общее число сообщений (None — без лимита)
        :return: список объектов Message
        """
        if not self.client:
            raise RuntimeError("Клиент не подключён. Вызовите connect() или используйте async with.")

        date_from = self._to_utc(date_from)
        date_to = self._to_utc(date_to)

        collected: List[Message] = []
        offset_id = 0

        while True:
            try:
                batch = await self.client.get_messages(
                    channel,
                    limit=limit_per_request,
                    offset_id=offset_id,
                    offset_date=date_to,
                )
            except FloodWaitError as e:
                print(f"[FloodWait] Ждём {e.seconds} сек...")
                await asyncio.sleep(e.seconds)
                continue

            if not batch:
                break

            stop = False
            for msg in batch:
                # Пропускаем пустые/сервисные сообщения без даты
                if not msg.date:
                    continue

                msg_date = self._to_utc(msg.date)

                if msg_date < date_from:
                    stop = True
                    break
                if msg_date > date_to:
                    continue

                collected.append(msg)
                if max_messages and len(collected) >= max_messages:
                    stop = True
                    break

            if stop:
                break

            # Сдвигаем offset для следующей пачки
            offset_id = batch[-1].id

            # Небольшая пауза, чтобы не получить FloodWait
            await asyncio.sleep(0.5)

        return collected

    async def get_multiple_channels(
            self,
            channels: List[Union[str, int]],
            date_from: datetime,
            date_to: datetime,
            max_messages_per_channel: Optional[int] = None,
    ) -> Dict[str, List[Message]]:
        """
        Получить сообщения из нескольких каналов за промежуток.

        :return: словарь {название/идентификатор канала: список сообщений}
        """
        results: Dict[str, List[Message]] = {}

        for ch in channels:
            print(f"→ Обработка канала: {ch}")
            try:
                messages = await self.get_channel_messages(
                    ch,
                    date_from,
                    date_to,
                    max_messages=max_messages_per_channel,
                )
                results[str(ch)] = messages
                print(f"   Получено сообщений: {len(messages)}")
            except Exception as e:
                print(f"   Ошибка при обработке {ch}: {e}")
                results[str(ch)] = []

        return results

    @staticmethod
    def messages_to_dicts(messages: List[Message]) -> List[Dict]:
        """Преобразует список Message в список обычных словарей."""
        result = []
        for m in messages:
            result.append({
                "id": m.id,
                "date": m.date.isoformat() if m.date else None,
                "text": m.text or "",
                "views": getattr(m, "views", None),
                "forwards": getattr(m, "forwards", None),
                "link": getattr(m, "link", lambda: None)(),
            })
        return result

# ---------------- Пример использования ----------------
async def main():


    channels = ["durov", "@telegram", "https://t.me/some_channel"]

    date_from = datetime(2024, 1, 1)
    date_to = datetime(2024, 6, 1)

    async with PrivateTgParser() as parser:
        data = await parser.get_multiple_channels(
            channels,
            date_from,
            date_to,
            max_messages_per_channel=500,
        )

        for channel, messages in data.items():
            print(f"\n=== {channel} ({len(messages)} сообщений) ===")
            for d in PrivateTgParser.messages_to_dicts(messages[:3]):
                print(f"[{d['date']}] {d['text'][:100]!r}")