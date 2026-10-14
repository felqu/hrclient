"""Простой HTTP-API парсинга вакансий из Telegram-каналов.

Запуск (из каталога backend):
    ../.venv/bin/python -m uvicorn app.api.parse_api:app --port 8000

Отдаёт:
    GET  /api/v1/health             — проверка доступности
    POST /api/v1/parse              — запуск парсинга, возвращает найденные вакансии
    POST /api/v1/vacancies/import   — то же, но в формате старого дашборда (frontend/index.html)
    GET  /api/v1/vacancies          — сохранённые вакансии в формате дашборда
    GET  /api/v1/vacancies/parsed   — сохранённые вакансии в полном формате
    GET  /api/v1/vacancies/export.xlsx — выгрузка всех сохранённых вакансий
    GET  /api/v1/analytics/dashboard — метрики откликов (заглушка)

Статический фронтенд (frontend/) монтируется на "/", поэтому страница
парсинга доступна по адресу http://localhost:8000/parse.html (same-origin,
CORS не нужен; CORS открыт для запуска страницы из nginx на другом порту).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time as stdlib_time
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.integrations.models.tg_models import JobVacancy
from app.integrations.sources import TelegramGateway
from app.pipeline_log import log_event, pipeline_run
from app.services.vacancy_export import vacancies_xlsx
from app.services.vacancy_store import VacancyStore, vacancy_id

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
    errors: list[str] = Field(default_factory=list, description="Сбои отдельных каналов (сеть и т.п.)")


class ImportRequest(BaseModel):
    """Тело старого эндпоинта дашборда (frontend/app.js)."""

    date_from: datetime | None = None
    date_to: datetime | None = None
    sources: list[str] = Field(default_factory=list, description='["hh","telegram"] как раньше')
    telegram_chats: list[str] = Field(default_factory=list, description="Каналы; иначе последний запуск/дефолт")
    chats: list[str] = Field(default_factory=list, description="Синоним telegram_chats")
    text: str | None = None
    backend: BackendName | None = None
    max_per_channel: int | None = Field(None, ge=1, le=10_000)


class VacancyRead(BaseModel):
    """Формат, который ждёт frontend/app.js (старый контракт VacancyRead)."""

    id: uuid.UUID
    source: str
    title: str
    company: str | None
    description: str
    url: str
    published_at: datetime | None


class DashboardMetrics(BaseModel):
    total_sent: int = 0
    viewed: int = 0
    invited: int = 0
    rejected: int = 0


_last_chats: list[str] = []


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


async def _run_parse(
    *,
    chats: list[str],
    backend: BackendName | None,
    date_from: date | datetime | None,
    date_to: date | datetime | None,
    text: str | None,
    max_per_channel: int | None,
) -> ParseResponse:
    global _last_chats

    with pipeline_run():
        now = datetime.now(timezone.utc)
        started = stdlib_time.perf_counter()
        log_event("parse.start", chats=chats, backend=backend, date_from=date_from,
                  date_to=date_to, text_filter=text, max_per_channel=max_per_channel or 500)
        try:
            gateway = TelegramGateway(
                chats=chats, backend=backend, max_per_channel=max_per_channel or 500,
            )
            vacancies = await gateway.search(
                date_from=_to_dt(date_from, now - timedelta(days=7)),
                date_to=_to_dt(date_to, now), text=text or None,
            )
        except Exception as exc:
            log_event("parse.failed", level=logging.ERROR, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        try:
            await asyncio.to_thread(VacancyStore().save, vacancies)
        except Exception as exc:
            log_event("parse.save_failed", level=logging.ERROR, exc_info=True)
            raise HTTPException(status_code=500, detail="Не удалось сохранить вакансии в DuckDB") from exc
        result = ParseResponse(
            count=len(vacancies),
            duration_ms=round((stdlib_time.perf_counter() - started) * 1000),
            chats=chats, vacancies=vacancies, errors=list(gateway.last_errors),
        )
        _last_chats = list(chats)
        log_event("parse.done", count=result.count, duration_ms=result.duration_ms, errors=result.errors)
        return result


def _resolve_import_chats(body: ImportRequest) -> list[str]:
    if body.telegram_chats:
        return body.telegram_chats
    if body.chats:
        return body.chats
    if _last_chats:
        return list(_last_chats)
    env_chats = os.getenv("TG_DEFAULT_CHATS", "")
    parsed = [c.strip() for c in env_chats.split(",") if c.strip()]
    return parsed or ["telegram"]


def _vacancy_to_read(vacancy: JobVacancy) -> VacancyRead:
    source = vacancy.source
    channel = source.channel_name if source else None
    if source and source.original_url:
        url = str(source.original_url)
    elif source and source.channel_url:
        url = str(source.channel_url)
    else:
        url = "#"
    return VacancyRead(
        id=vacancy_id(vacancy),
        source=channel or "telegram",
        title=vacancy.title,
        company=vacancy.company.name if vacancy.company else None,
        description=vacancy.raw_text,
        url=url,
        published_at=(
            datetime.combine(vacancy.published_date, time.min, tzinfo=timezone.utc)
            if vacancy.published_date
            else None
        ),
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/parse", response_model=ParseResponse)
async def parse_vacancies(body: ParseRequest) -> ParseResponse:
    return await _run_parse(
        chats=body.chats,
        backend=body.backend,
        date_from=body.date_from,
        date_to=body.date_to,
        text=body.text,
        max_per_channel=body.max_per_channel,
    )


@router.post("/vacancies/import")
async def import_vacancies(body: ImportRequest) -> dict:
    if body.sources and "telegram" not in body.sources:
        return {"ok": True, "count": 0, "duration_ms": 0, "chats": [], "detail": "Источник telegram не запрошен"}
    chats = _resolve_import_chats(body)
    result = await _run_parse(
        chats=chats,
        backend=body.backend,
        date_from=body.date_from,
        date_to=body.date_to,
        text=body.text,
        max_per_channel=body.max_per_channel,
    )
    if result.errors and result.count == 0:
        detail = "Не удалось получить данные: " + "; ".join(result.errors)
    elif result.errors:
        detail = (
            f"Импорт завершён: найдено вакансий {result.count}; "
            f"сбои: {'; '.join(result.errors)}"
        )
    else:
        detail = f"Импорт завершён: найдено вакансий {result.count}"
    return {
        "ok": True,
        "count": result.count,
        "duration_ms": result.duration_ms,
        "chats": result.chats,
        "detail": detail,
        "errors": result.errors,
    }


@router.get("/vacancies", response_model=list[VacancyRead])
async def list_vacancies() -> list[VacancyRead]:
    vacancies = await asyncio.to_thread(VacancyStore().list)
    return [_vacancy_to_read(v) for v in vacancies]


@router.get("/vacancies/parsed", response_model=list[JobVacancy])
async def list_parsed_vacancies() -> list[JobVacancy]:
    return await asyncio.to_thread(VacancyStore().list)


@router.get("/vacancies/export.xlsx")
def export_vacancies_xlsx() -> Response:
    with pipeline_run():
        log_event("export.start")
        try:
            vacancies = VacancyStore().list()
            content = vacancies_xlsx(vacancies)
        except Exception as exc:
            log_event("export.failed", level=logging.ERROR, exc_info=True)
            raise HTTPException(status_code=500, detail="Не удалось создать XLSX. Подробности в pipeline.log") from exc
        filename = f"vacancies-{datetime.now(timezone.utc):%Y-%m-%d}.xlsx"
        log_event("export.done", count=len(vacancies), bytes=len(content), filename=filename)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


@router.get("/analytics/dashboard", response_model=DashboardMetrics)
async def analytics_dashboard() -> DashboardMetrics:
    return DashboardMetrics()


app = FastAPI(title="HR Client Parse API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(router)
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.api.parse_api:app", host="127.0.0.1", port=8090)
