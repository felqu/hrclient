from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel

from app.domain.models import VacancySource


class NormalizedVacancy(BaseModel):
    source: VacancySource
    external_id: str
    title: str
    company: str | None = None
    description: str
    url: str
    published_at: datetime
    payload: dict = {}


class SourceGateway(ABC):
    @abstractmethod
    async def search(self, *, date_from: datetime, date_to: datetime, text: str | None = None) -> list[NormalizedVacancy]:
        """Fetch and normalize vacancies. Pagination and deduplication are adapter concerns."""


class HHGateway(SourceGateway):
    async def search(self, *, date_from: datetime, date_to: datetime, text: str | None = None) -> list[NormalizedVacancy]:
        # TODO: Call official hh.ru API with OAuth token and date_from/date_to.
        # API particulars differ for applicant/employer search endpoints.
        return []


class TelegramGateway(SourceGateway):
    def __init__(self, chats: list[str]) -> None:
        self.chats = chats

    async def search(self, *, date_from: datetime, date_to: datetime, text: str | None = None) -> list[NormalizedVacancy]:
        # TODO: Use Telethon to read configured public/private dialogs and filter message.date.
        # Do not bypass Telegram terms of service or user consent requirements.
        return []
