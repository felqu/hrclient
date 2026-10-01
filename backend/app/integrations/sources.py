from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import asyncio
import os
import re
from datetime import datetime, timezone
from typing import List, Optional, Union

import pandas as pd
from dotenv import load_dotenv

#internal imports
from tg_parser import TgParser
from models.tg_models import JobVacancy

load_dotenv()



class SourceGateway(ABC):
    @abstractmethod
    async def search(self, *, date_from: datetime, date_to: datetime, text: str | None = None) -> list[NormalizedJobVacancy]:
        """Fetch and normalize vacancies. Pagination and deduplication are adapter concerns."""


class HHGateway(SourceGateway):
    async def search(self, *, date_from: datetime, date_to: datetime, text: str | None = None) -> list[NormalizedJobVacancy]:
        # TODO: Call official hh.ru API with OAuth token and date_from/date_to.
        # API particulars differ for applicant/employer search endpoints.
        return []




class TelegramGateway(TgParser, SourceGateway):
    """
    Шлюз-источник вакансий из Telegram-каналов.

    :param chats: список каналов (username, @name, t.me/..., id)
    :param session_name: имя файла сессии Telethon
    :param max_per_channel: сколько сообщений максимум тянуть с канала
    :param JobVacancy_keywords: regex-паттерн «это вакансия»
    """

    def __init__(
        self,
        chats: List[str],
        *,
        api_id: Optional[str] = None,
        api_hash: Optional[str] = None,
        phone: Optional[str] = None,
        session_name: str = "tg_parser",
        max_per_channel: Optional[int] = 500,
        JobVacancy_keywords: str = r"(вакансия|JobVacancy|hiring|ищем|требуется|job\s*offer)",
    ) -> None:
        self.chats = chats
        self.api_id = api_id or os.getenv("TG_API_ID")
        self.api_hash = api_hash or os.getenv("TG_API_HASH")
        self.phone = phone or os.getenv("TG_PHONE_NUM")
        self.session_name = session_name
        self.max_per_channel = max_per_channel
        self._JobVacancy_re = re.compile(JobVacancy_keywords, re.IGNORECASE)

    # --- контекстный менеджер (удобно для тестов и скриптов) ---
    async def __aenter__(self) -> "TelegramGateway":
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._disconnect()

    # --- основной метод, требуемый SourceGateway ---
    async def search(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        text: Optional[str] = None,
    ) -> List[JobVacancy]:
        """
        Возвращает список вакансий из указанных чатов за промежуток [date_from, date_to].
        Если text передан — фильтруем по подстроке (case-insensitive).
        """
        await self._connect()
        try:
            vacancies: List[JobVacancy] = []

            for chat in self.chats:
                print(f"→ Обработка канала: {chat}")
                try:
                    messages = await self._get_channel_messages(
                        chat,
                        date_from,
                        date_to,
                        max_messages=self.max_per_channel,
                    )
                except Exception as e:
                    print(f"   Ошибка при обработке {chat}: {e}")
                    continue

                print(f"   Получено сообщений: {len(messages)}")
                for msg in messages:
                    JobVacancy = self._parse_JobVacancy(chat, msg)
                    if JobVacancy is None:
                        continue
                    if text and text.lower() not in JobVacancy.text.lower():
                        continue
                    vacancies.append(JobVacancy)

            return vacancies
        finally:
            await self._disconnect()

    def _parse_Vacancy(self, channel: Union[str, int], msg: Message) -> Optional[JobVacancy]:
        """
        not yet
        """
        text = (msg.text or "").strip()
        if not text:
            return None
        if not self._JobVacancy_re.search(text):
            return None

        title = self._guess_title(text)
        url = self._message_url(channel, msg)

        return JobVacancy(
            id=f"tg:{channel}:{msg.id}",
            channel=str(channel),
            message_id=msg.id,
            posted_at=self._to_utc(msg.date),
            title=title,
            company=None,       # TODO: извлечь из текста / LLM
            location=None,      # TODO
            salary=None,        # TODO
            text=text,
            url=url,
        )

    @staticmethod
    def _guess_title(text: str) -> Optional[str]:
        # первая непустая строка, обрезанная до 120 символов
        for line in text.splitlines():
            line = line.strip(" •-—\t")
            if line:
                return line[:120]
        return None

    @staticmethod
    def _message_url(channel: Union[str, int], msg: Message) -> Optional[str]:
        try:
            if msg.link:
                return msg.link
        except Exception:
            pass
        # fallback
        if isinstance(channel, str):
            slug = channel.replace("https://t.me/", "").replace("t.me/", "").lstrip("@")
            return f"https://t.me/{slug}/{msg.id}"
        return None


# ---------- Экспорт датасета (пока мок) ----------
def vacancies_to_dataframe(vacancies: List[JobVacancy]) -> pd.DataFrame:
    """Превращает список JobVacancy в pandas DataFrame."""
    if not vacancies:
        return pd.DataFrame(
            columns=[
                "id", "source", "channel", "message_id", "posted_at",
                "title", "company", "location", "salary", "text", "url",
            ]
        )
    return pd.DataFrame([v.model_dump() for v in vacancies])


def export_vacancies(
    vacancies: List[JobVacancy],
    path: str = "vacancies.csv",
) -> pd.DataFrame:
    """
    Сохраняет вакансии в CSV или XLSX в зависимости от расширения.
    Возвращает DataFrame — удобно для тестов и отладки.
    """
    df = vacancies_to_dataframe(vacancies)

    if path.lower().endswith(".csv"):
        df.to_csv(path, index=False)
    elif path.lower().endswith((".xlsx", ".xls")):
        df.to_excel(path, index=False)
    else:
        raise ValueError(f"Неподдержириваемое расширение файла: {path}")

    print(f"💾 Сохранено {len(df)} вакансий в {path}")
    return df


async def _main() -> None:
    chats = [
        # "durov",
        # "@some_JobVacancy_channel",
        # "https://t.me/another_channel",
    ]

    date_from = datetime(2024, 1, 1)
    date_to = datetime(2024, 6, 1)

    gateway = TelegramGateway(
        chats=chats,
        max_per_channel=500,
    )

    vacancies = await gateway.search(date_from=date_from, date_to=date_to)
    print(f"Итого вакансий: {len(vacancies)}")

    # Датасет
    export_vacancies(vacancies, "vacancies.csv")
    export_vacancies(vacancies, "vacancies.xlsx")


if __name__ == "__main__":
    asyncio.run(_main())