from __future__ import annotations

import argparse
import asyncio
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal, Protocol

from dotenv import load_dotenv

from .models.tg_models import (
    EmploymentType,
    ExperienceLevel,
    JobVacancy,
    Salary,
    SourceInfo,
    WorkFormat,
)

load_dotenv()

BackendName = Literal["tg_parser", "private_tg_parser"]

DEFAULT_VACANCY_KEYWORDS = r"(ваканси\w*|hiring|ищем|требуется|job\s*offer|vacancy)"


# --------------------------------------------------------------------------
# Бэкенды: способ получения сообщений из Telegram
# --------------------------------------------------------------------------


class TgMessageBackend(Protocol):
    """Общий контракт двух парсеров: tg_parser (tgscraper) и private_tg_parser (Telethon)."""

    name: BackendName

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def fetch(
        self,
        channel: str,
        date_from: datetime,
        date_to: datetime,
        max_messages: int | None,
    ) -> list[Any]: ...


class ScraperBackend:
    """tg_parser: публичные каналы через tgscraper, без авторизации."""

    name: BackendName = "tg_parser"

    def __init__(self) -> None:
        from .tg_parser import TgParser

        self._parser = TgParser()

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetch(
        self,
        channel: str,
        date_from: datetime,
        date_to: datetime,
        max_messages: int | None,
    ) -> list[Any]:
        # tgscraper синхронный и блокирующий — уводим в отдельный поток.
        return await asyncio.to_thread(
            self._parser.get_channel_messages, channel, date_from, date_to, max_messages
        )


class TelethonBackend:
    """private_tg_parser: приватные/публичные каналы через Telethon (нужен TG_API_ID/TG_API_HASH)."""

    name: BackendName = "private_tg_parser"

    def __init__(
        self,
        *,
        session_name: str = "tg_parser",
        api_id: str | None = None,
        api_hash: str | None = None,
        phone: str | None = None,
    ) -> None:
        from .private_tg_parser import PrivateTgParser

        self._parser = PrivateTgParser(
            session_name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
        )

    async def open(self) -> None:
        await self._parser.connect()

    async def close(self) -> None:
        await self._parser.disconnect()

    async def fetch(
        self,
        channel: str,
        date_from: datetime,
        date_to: datetime,
        max_messages: int | None,
    ) -> list[Any]:
        return await self._parser.get_channel_messages(
            channel, date_from, date_to, max_messages=max_messages
        )


def build_backend(
    backend: BackendName | None = None,
    *,
    session_name: str = "tg_parser",
    api_id: str | None = None,
    api_hash: str | None = None,
    phone: str | None = None,
) -> TgMessageBackend:
    chosen: BackendName = backend or os.getenv("TG_BACKEND", "tg_parser")  # type: ignore[assignment]
    if chosen == "tg_parser":
        return ScraperBackend()
    if chosen == "private_tg_parser":
        return TelethonBackend(
            session_name=session_name, api_id=api_id, api_hash=api_hash, phone=phone
        )
    raise ValueError(
        f"Неизвестный backend: {chosen!r}; ожидается 'tg_parser' или 'private_tg_parser'"
    )


# --------------------------------------------------------------------------
# Gateway-контракт
# --------------------------------------------------------------------------


class SourceGateway(ABC):
    @abstractmethod
    async def search(
        self, *, date_from: datetime, date_to: datetime, text: str | None = None
    ) -> list[JobVacancy]:
        """Fetch and normalize vacancies. Pagination and deduplication are adapter concerns."""


class HHGateway(SourceGateway):
    async def search(
        self, *, date_from: datetime, date_to: datetime, text: str | None = None
    ) -> list[JobVacancy]:
        # TODO: Call official hh.ru API with OAuth token (HH_CLIENT_ID/HH_CLIENT_SECRET).
        # API particulars differ for applicant/employer search endpoints.
        return []


class TelegramGateway(SourceGateway):
    """
    Шлюз-источник вакансий из Telegram-каналов.

    :param chats: список каналов (username, @name, t.me/..., id)
    :param backend: 'tg_parser' (публичные каналы, tgscraper)
                    или 'private_tg_parser' (Telethon, приватные каналы);
                    по умолчанию берётся из env TG_BACKEND
    :param max_per_channel: сколько сообщений максимум тянуть с канала
    :param vacancy_keywords: regex-паттерн «это вакансия»
    """

    def __init__(
        self,
        chats: list[str],
        *,
        backend: BackendName | None = None,
        session_name: str = "tg_parser",
        api_id: str | None = None,
        api_hash: str | None = None,
        phone: str | None = None,
        max_per_channel: int | None = 500,
        vacancy_keywords: str = DEFAULT_VACANCY_KEYWORDS,
    ) -> None:
        self.chats = list(chats)
        self.max_per_channel = max_per_channel
        self._vacancy_re = re.compile(vacancy_keywords, re.IGNORECASE)
        self._backend = build_backend(
            backend,
            session_name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
        )
        self._opened = False
        self._in_context = False

    # --- контекстный менеджер (удобно для тестов и скриптов) ---
    async def __aenter__(self) -> TelegramGateway:
        self._in_context = True
        await self._open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._in_context = False
        await self._close()

    async def _open(self) -> None:
        if not self._opened:
            await self._backend.open()
            self._opened = True

    async def _close(self) -> None:
        if self._opened:
            self._opened = False
            await self._backend.close()

    # --- основной метод, требуемый SourceGateway ---
    async def search(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        text: str | None = None,
    ) -> list[JobVacancy]:
        """Возвращает вакансии из self.chats за [date_from, date_to] (дедупликация включена)."""
        start, end = _normalize_range(date_from, date_to)
        if self._in_context:
            await self._open()
            return await self._collect(start, end, text)

        await self._open()
        try:
            return await self._collect(start, end, text)
        finally:
            await self._close()

    async def _collect(
        self, start: datetime, end: datetime, text: str | None
    ) -> list[JobVacancy]:
        vacancies: list[JobVacancy] = []
        seen: set[tuple[str, str]] = set()

        for chat in self.chats:
            try:
                messages = await self._backend.fetch(
                    chat, start, end, self.max_per_channel
                )
            except Exception as exc:  # noqa: BLE001 — сбой одного канала не должен ронять импорт
                print(f"   Ошибка при обработке {chat}: {exc}")
                continue

            for msg in messages:
                vacancy = self._parse_vacancy(chat, msg, start, end)
                if vacancy is None:
                    continue
                source = vacancy.source
                key = (
                    source.channel_name if source else str(chat),
                    source.message_id if source else str(id(msg)),
                )
                if key in seen:
                    continue
                seen.add(key)
                if text and text.lower() not in vacancy.raw_text.lower():
                    continue
                vacancies.append(vacancy)

        return vacancies

    def _parse_vacancy(
        self, channel: str, msg: Any, start: datetime, end: datetime
    ) -> JobVacancy | None:
        text = (getattr(msg, "text", "") or "").strip()
        if not text:
            return None
        if not self._vacancy_re.search(text):
            return None

        posted = _to_utc(getattr(msg, "date", None))
        start = _to_utc(start)
        end = _to_utc(end)
        if posted is None or (start and posted < start) or (end and posted > end):
            return None

        msg_id = getattr(msg, "id", None)
        channel_url = _channel_url(channel)
        return JobVacancy(
            title=_guess_title(text) or "Вакансия",
            source=SourceInfo(
                channel_name=str(channel),
                channel_url=channel_url,
                original_url=_message_url(msg, msg_id, channel_url),
                message_id=str(msg_id) if msg_id is not None else None,
            ),
            work_format=_detect_work_format(text),
            employment_type=_detect_employment_type(text),
            experience_level=_detect_experience_level(text),
            location=None,  # TODO: извлекать из текста (LLM)
            company=None,  # TODO: извлекать из текста (LLM)
            salary=_extract_salary(text),
            raw_text=text,
            hashtags=_extract_hashtags(msg, text),
            published_date=posted.date(),
            is_active=True,
        )


# --------------------------------------------------------------------------
# Нормализация сообщений двух разных парсеров
# --------------------------------------------------------------------------


def _guess_title(text: str) -> str | None:
    # первая непустая строка, обрезанная до 120 символов
    for line in text.splitlines():
        line = line.strip(" •-—\t")
        if line:
            return line[:120]
    return None


def _to_utc(value: Any) -> datetime | None:
    """datetime | ISO-строка -> aware UTC; не-распознанное -> None."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                value = datetime.strptime(value[:10], "%Y-%m-%d")
            except ValueError:
                return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_range(date_from: datetime, date_to: datetime) -> tuple[datetime, datetime]:
    """Приводит границы к UTC; полночь в date_to трактуется как конец дня (включительно)."""
    start = _to_utc(date_from) or datetime.min.replace(tzinfo=timezone.utc)
    end = _to_utc(date_to) or datetime.max.replace(tzinfo=timezone.utc)
    if end.time() == time.min:
        end = end + timedelta(days=1) - timedelta(microseconds=1)
    return start, end


def _channel_url(channel: str) -> str | None:
    """https://t.me/<slug> для username/ссылки, None для числовых id."""
    raw = str(channel).strip()
    if raw.startswith(("http://", "https://")):
        return raw
    slug = raw.lstrip("@")
    if re.fullmatch(r"[A-Za-z0-9_]+", slug):
        return f"https://t.me/{slug}"
    return None


def _message_url(msg: Any, msg_id: Any, channel_url: str | None) -> str | None:
    # tgscraper отдаёт готовый .url; у Telethon его нет — собираем сами.
    url = getattr(msg, "url", None)
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    if channel_url and msg_id is not None:
        return f"{channel_url}/{msg_id}"
    return None


def _detect_work_format(text: str) -> WorkFormat:
    lowered = text.lower()
    if "гибрид" in lowered or "hybrid" in lowered:
        return WorkFormat.HYBRID
    if any(key in lowered for key in ("удалён", "удален", "remote")):
        return WorkFormat.REMOTE
    if any(key in lowered for key in ("офис", "office", "on-site", "onsite")):
        return WorkFormat.OFFICE
    return WorkFormat.UNKNOWN


def _detect_employment_type(text: str) -> EmploymentType:
    lowered = text.lower()
    # порядок важен: «неполный» содержит «полный»
    if any(key in lowered for key in ("частичн", "part time", "part-time", "неполный")):
        return EmploymentType.PART_TIME
    if any(key in lowered for key in ("стажиров", "internship")):
        return EmploymentType.INTERNSHIP
    if any(key in lowered for key in ("контракт", "contract")):
        return EmploymentType.CONTRACT
    if any(key in lowered for key in ("полная занятость", "full time", "full-time", "полный день")):
        return EmploymentType.FULL_TIME
    return EmploymentType.UNKNOWN


def _detect_experience_level(text: str) -> ExperienceLevel:
    lowered = text.lower()
    if any(key in lowered for key in ("lead", "лид")):
        return ExperienceLevel.LEAD
    if any(key in lowered for key in ("senior", "сеньор", "сеньер", "синьор")):
        return ExperienceLevel.SENIOR
    if any(key in lowered for key in ("middle", "мидл", "миддл")):
        return ExperienceLevel.MIDDLE
    if any(key in lowered for key in ("junior", "джун", "джуниор")):
        return ExperienceLevel.JUNIOR
    if any(key in lowered for key in ("intern", "стажёр", "стажер", "интерн")):
        return ExperienceLevel.INTERN
    return ExperienceLevel.UNKNOWN


_NUM_TOKEN_RE = re.compile(r"\d+(?:[\s\u00a0]\d{3})*")
_SALARY_MARKER_RE = re.compile(
    r"(?:з/п|зарплат\w*|оплат\w*|доход)\s*[:\-–—]?\s*(?P<body>.{0,80})", re.IGNORECASE
)
_SALARY_CURRENCY_RE = re.compile(
    r"\d+(?:[\s\u00a0]\d{3})+(?:\s*[-–—]\s*\d+(?:[\s\u00a0]\d{3})+)?\s*(?:₽|руб)", re.IGNORECASE
)
_SALARY_UNIT_RE = re.compile(r"тыс\.?|(?<![A-Za-zА-Яа-я])(?:k|к)(?![A-Za-zА-Яа-я])", re.IGNORECASE)


def _extract_salary(text: str) -> Salary | None:
    """Грубая эвристика: «з/п от 100 000 до 150 000 ₽» / «150-200к». Сложные случаи — TODO (LLM)."""
    match = _SALARY_MARKER_RE.search(text) or _SALARY_CURRENCY_RE.search(text)
    if not match:
        return None
    body = match.group("body") if "body" in match.groupdict() else match.group(0)

    numbers: list[int] = []
    for token in _NUM_TOKEN_RE.findall(body):
        value = int(re.sub(r"[\s\u00a0]", "", token))
        if value <= 10_000_000:
            numbers.append(value)
    if not numbers:
        return None

    if _SALARY_UNIT_RE.search(body):
        numbers = [n * 1000 if n < 10_000 else n for n in numbers]

    minimum = numbers[0]
    maximum = numbers[1] if len(numbers) > 1 and numbers[1] > minimum else None

    currency = "RUB"
    if "$" in body or "usd" in body.lower():
        currency = "USD"
    elif "€" in body or "eur" in body.lower():
        currency = "EUR"

    return Salary(
        min_amount=minimum,
        max_amount=maximum,
        currency=currency,
        period="month",
        raw_text=match.group(0).strip(),
    )


def _extract_hashtags(msg: Any, text: str) -> list[str]:
    hashtags = list(dict.fromkeys(re.findall(r"#(\w+)", text, flags=re.UNICODE)))
    for tag in getattr(msg, "hashtags", None) or []:
        tag = str(tag).lstrip("#")
        if tag and tag not in hashtags:
            hashtags.append(tag)
    return hashtags[:20]


# --------------------------------------------------------------------------
# Экспорт датасета (pandas импортируется лениво: API-сервису он не нужен)
# --------------------------------------------------------------------------

_EXPORT_COLUMNS = [
    "source",
    "channel",
    "message_id",
    "url",
    "title",
    "company",
    "location",
    "work_format",
    "employment_type",
    "experience_level",
    "salary",
    "published_date",
    "hashtags",
    "raw_text",
]


def _salary_to_str(salary: Salary | None) -> str | None:
    if salary is None:
        return None
    if salary.min_amount and salary.max_amount:
        return f"{salary.min_amount}–{salary.max_amount} {salary.currency}"
    if salary.min_amount:
        return f"от {salary.min_amount} {salary.currency}"
    return salary.raw_text


def vacancies_to_dataframe(vacancies: list[JobVacancy]) -> Any:
    """Превращает список JobVacancy в pandas DataFrame (разворачивает вложенные модели)."""
    import pandas as pd

    if not vacancies:
        return pd.DataFrame(columns=_EXPORT_COLUMNS)

    rows = []
    for v in vacancies:
        source = v.source
        rows.append(
            {
                "source": "telegram",
                "channel": source.channel_name if source else None,
                "message_id": source.message_id if source else None,
                "url": str(source.original_url) if source and source.original_url else None,
                "title": v.title,
                "company": v.company.name if v.company else None,
                "location": v.location,
                "work_format": v.work_format.value,
                "employment_type": v.employment_type.value,
                "experience_level": v.experience_level.value,
                "salary": _salary_to_str(v.salary),
                "published_date": v.published_date.isoformat() if v.published_date else None,
                "hashtags": ",".join(v.hashtags),
                "raw_text": v.raw_text,
            }
        )
    return pd.DataFrame(rows, columns=_EXPORT_COLUMNS)


def export_vacancies(vacancies: list[JobVacancy], path: str = "vacancies.csv") -> Any:
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
        raise ValueError(f"Неподдерживаемое расширение файла: {path}")

    print(f"Сохранено {len(df)} вакансий в {path}")
    return df


async def _main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Сбор вакансий из Telegram-каналов")
    parser.add_argument(
        "--chats", nargs="+", required=True, help="Каналы: @name, t.me/... или username"
    )
    parser.add_argument(
        "--backend",
        choices=("tg_parser", "private_tg_parser"),
        default=None,
        help="Парсер (по умолчанию env TG_BACKEND или tg_parser)",
    )
    parser.add_argument("--date-from", default="2024-01-01", help="ISO-дата, YYYY-MM-DD")
    parser.add_argument("--date-to", default="2024-06-01", help="ISO-дата, YYYY-MM-DD")
    parser.add_argument("--text", default=None, help="Дополнительный фильтр по подстроке")
    parser.add_argument("--max-per-channel", type=int, default=500)
    parser.add_argument("--out", default="vacancies.csv", help=".csv или .xlsx")
    args = parser.parse_args(argv)

    gateway = TelegramGateway(
        chats=args.chats,
        backend=args.backend,
        max_per_channel=args.max_per_channel,
    )
    vacancies = await gateway.search(
        date_from=datetime.fromisoformat(args.date_from),
        date_to=datetime.fromisoformat(args.date_to),
        text=args.text,
    )
    print(f"Итого вакансий: {len(vacancies)}")
    export_vacancies(vacancies, args.out)


if __name__ == "__main__":
    asyncio.run(_main())
