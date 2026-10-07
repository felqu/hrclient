"""Простой HTTP-API парсинга вакансий из Telegram-каналов.

Запуск (из каталога backend):
    ../.venv/bin/python -m uvicorn app.api.parse_api:app --port 8000

Отдаёт:
    GET  /api/v1/health   — проверка доступности
    POST /api/v1/parse    — запуск парсинга, возвращает найденные вакансии

Статический фронтенд (frontend/) монтируется на "/", поэтому страница
парсинга доступна по адресу http://localhost:8000/parse.html (same-origin,
CORS не нужен; CORS открыт для запуска страницы из nginx на другом порту).
"""
from __future__ import annotations

import time as stdlib_time
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.integrations.models.tg_models import JobVacancy
from app.integrations.sources import TelegramGateway

BackendName = Literal["tg_parser", "private_tg_parser"]

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

router = APIRouter(prefix="/api/v1", tags=["parse"])


class ParseRequest(BaseModel):
    chats: list[str] = Field(..., min_length=1, description="Каналы: username, @name или t.me/...")
    backend: BackendName | None = Field(None, description="tg_parser | private_tg_parser; иначе TG_BACKEND")
    date_from: date | datetime | None = Field(None, description="YYYY-MM-DD или ISO; иначе -7 дней")
    date_to: date | datetime | None = Field(None, description="YYYY-MM-DD или ISO; иначе сейчас")
    text: str | None = Field(None, description="Дополнительный фильтр по подстроке")
    max_per_channel: int | None = Field(None, ge=1, le=10_000, description="Лимит сообщений на канал")


class ParseResponse(BaseModel):
    ok: bool = True
    count: int
    duration_ms: int
    chats: list[str]
    vacancies: list[JobVacancy]


def _to_dt(value: date | datetime | None, default: datetime) -> datetime:
    """date → полночь UTC; naive datetime → UTC; None → default."""
    if value is None:
        return default
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.combine(value, time.min)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/parse", response_model=ParseResponse)
async def parse_vacancies(body: ParseRequest) -> ParseResponse:
    now = datetime.now(timezone.utc)
    gateway = TelegramGateway(
        chats=body.chats,
        backend=body.backend,
        max_per_channel=body.max_per_channel or 500,
    )
    started = stdlib_time.perf_counter()
    try:
        vacancies = await gateway.search(
            date_from=_to_dt(body.date_from, now - timedelta(days=7)),
            date_to=_to_dt(body.date_to, now),
            text=body.text or None,
        )
    except Exception as exc:  # noqa: BLE001 — транслируем ошибку парсера клиенту страницы
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ParseResponse(
        count=len(vacancies),
        duration_ms=round((stdlib_time.perf_counter() - started) * 1000),
        chats=body.chats,
        vacancies=vacancies,
    )


app = FastAPI(title="HR Client Parse API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.api.parse_api:app", host="127.0.0.1", port=8000)
