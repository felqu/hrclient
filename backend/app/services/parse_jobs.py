"""Background parsing with thread-safe snapshots for the Streamlit UI."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time as day_time, timezone
from threading import Event, RLock, Thread
from typing import Any

from app.integrations.models.tg_models import JobVacancy
from app.integrations.sources import ParsingCancelled, TelegramGateway
from app.pipeline_log import log_event, pipeline_run
from app.services.vacancy_store import VacancyStore


@dataclass(frozen=True)
class ParseSettings:
    chats: list[str]
    date_from: date
    date_to: date
    backend: str = "tg_parser"
    text: str | None = None
    max_per_channel: int = 500

    def validate(self) -> None:
        if not self.chats or any(not chat.strip() for chat in self.chats):
            raise ValueError("Укажите хотя бы один канал.")
        if self.date_from > self.date_to:
            raise ValueError("Дата начала должна быть не позже даты окончания.")
        if self.backend not in {"tg_parser", "private_tg_parser"}:
            raise ValueError("Неизвестный парсер Telegram.")
        if not 1 <= self.max_per_channel <= 10_000:
            raise ValueError("Лимит сообщений должен быть от 1 до 10 000.")


class ParseJob:
    def __init__(self, settings: ParseSettings):
        self.id = uuid.uuid4().hex[:12]
        self.settings = settings
        self.lock = RLock()
        self.cancel = Event()
        self.finished = Event()
        self.started = time.monotonic()
        self.ended: float | None = None
        self.state = "queued"
        self.stage = "Подготовка к запуску"
        self.channel = ""
        self.channel_messages = 0
        self.channel_processed = 0
        self.completed_channels = 0
        self.received = 0
        self.processed = 0
        self.llm_requests = 0
        self.llm_errors = 0
        self.skipped = 0
        self.saved = 0
        self.vacancies: list[JobVacancy] = []
        self.errors: list[str] = []
        self.events: deque[dict[str, Any]] = deque(maxlen=300)

    def on_event(self, event: str, data: dict[str, Any]) -> None:
        with self.lock:
            self.events.append({"time": datetime.now().strftime("%H:%M:%S"),
                                "event": event, "details": data})
            if event == "channel.fetch.start":
                self.channel = str(data["channel"])
                self.channel_processed = self.channel_messages = 0
                self.stage = f"Получение сообщений: {self.channel}"
            elif event == "channel.fetch.done":
                self.channel_messages = data["messages"]
                self.received += data["messages"]
                self.stage = f"Обработка {data['messages']} сообщений: {self.channel}"
            elif event == "channel.fetch.failed":
                self.completed_channels += 1
                self.errors.append(f"Не удалось получить канал {data['channel']}")
            elif event == "message.processed":
                self.processed += 1
                self.channel_processed += 1
                self.stage = f"Обработано {self.channel_processed}/{self.channel_messages}: {self.channel}"
            elif event == "message.skipped":
                self.skipped += 1
            elif event == "llm.request":
                self.llm_requests += 1
                self.stage = f"LLM обрабатывает сообщение {data.get('message_id')} · {data.get('channel')}"
            elif event in {"llm.failed", "llm.invalid_response", "llm.invalid_json"}:
                self.llm_errors += 1
                self.errors.append(f"{data.get('channel')}, сообщение {data.get('message_id')}: "
                                   f"{data.get('error', 'ошибка запроса к LLM')}")
            elif event == "vacancy.accepted":
                self.vacancies.append(JobVacancy.model_validate(data["vacancy"]))
            elif event == "channel.done":
                self.completed_channels += 1
                self.channel_messages = self.channel_processed = 0
            elif event == "db.save.start":
                self.stage = "Сохранение вакансий в DuckDB"
            elif event == "db.save.done":
                self.saved = data["count"]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            fraction = min(self.channel_processed / self.channel_messages, 1) if self.channel_messages else 0
            progress = min((self.completed_channels + fraction) / len(self.settings.chats), 1) * .95
            if self.state in {"completed", "completed_with_errors"}:
                progress = 1.0
            return {
                "id": self.id, "state": self.state, "stage": self.stage,
                "terminal": self.finished.is_set(), "progress": progress,
                "elapsed": (self.ended or time.monotonic()) - self.started,
                "received": self.received, "processed": self.processed,
                "llm_requests": self.llm_requests, "llm_errors": self.llm_errors,
                "skipped": self.skipped, "found": len(self.vacancies), "saved": self.saved,
                "completed_channels": self.completed_channels,
                "total_channels": len(self.settings.chats),
                "chats": list(self.settings.chats), "errors": list(self.errors),
                "events": list(self.events),
            }


class ParseJobManager:
    def __init__(self, store: VacancyStore | None = None):
        self.store = store or VacancyStore()
        self.jobs: dict[str, ParseJob] = {}
        self.lock = RLock()

    def active_id(self) -> str | None:
        with self.lock:
            return next((job.id for job in self.jobs.values() if not job.finished.is_set()), None)

    def start(self, settings: ParseSettings) -> str:
        settings.validate()
        with self.lock:
            if self.active_id():
                raise ValueError("Парсинг уже идёт. Дождитесь завершения или остановите текущий запуск.")
            while len(self.jobs) >= 20:
                del self.jobs[next(iter(self.jobs))]
            job = ParseJob(settings)
            self.jobs[job.id] = job
            Thread(target=self._run, args=(job,), daemon=True, name=f"parse-{job.id}").start()
            return job.id

    def snapshot(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
        return job.snapshot() if job else None

    def history(self) -> list[dict[str, Any]]:
        with self.lock:
            return [job.snapshot() for job in reversed(list(self.jobs.values()))]

    def stop(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
        if job and not job.finished.is_set():
            with job.lock:
                job.cancel.set()
                job.state = "stopping"

    def _run(self, job: ParseJob) -> None:
        with pipeline_run(run_id=job.id, on_event=job.on_event):
            with job.lock:
                job.state = "stopping" if job.cancel.is_set() else "running"
            log_event("parse.start", chats=job.settings.chats, backend=job.settings.backend)
            try:
                vacancies, errors = asyncio.run(self._search(job))
                self.store.save(vacancies)
                with job.lock:
                    job.errors = errors
                    job.state = "completed_with_errors" if errors else "completed"
                    job.stage = "Парсинг завершён с ошибками" if errors else "Парсинг завершён"
                log_event("parse.done", count=len(vacancies), errors=errors,
                          duration_ms=round((time.monotonic() - job.started) * 1000))
            except ParsingCancelled:
                try:
                    self.store.save(job.vacancies)
                    with job.lock:
                        job.state = "cancelled"
                        job.stage = "Остановлено. Найденные вакансии сохранены"
                    log_event("parse.cancelled", count=len(job.vacancies))
                except Exception as exc:
                    self._fail(job, exc)
            except Exception as exc:
                self._fail(job, exc)
            finally:
                with job.lock:
                    job.ended = time.monotonic()
                    job.finished.set()

    def _fail(self, job: ParseJob, exc: Exception) -> None:
        log_event("parse.failed", level=logging.ERROR, exc_info=True, error=str(exc))
        with job.lock:
            job.state = "failed"
            job.stage = "Парсинг завершился с ошибкой"
            job.errors.append(str(exc) or type(exc).__name__)

    async def _search(self, job: ParseJob) -> tuple[list[JobVacancy], list[str]]:
        settings = job.settings
        gateway = TelegramGateway(chats=settings.chats, backend=settings.backend,
                                  max_per_channel=settings.max_per_channel,
                                  cancel_requested=job.cancel.is_set)
        try:
            vacancies = await gateway.search(
                date_from=datetime.combine(settings.date_from, day_time.min, tzinfo=timezone.utc),
                date_to=datetime.combine(settings.date_to, day_time.max, tzinfo=timezone.utc),
                text=settings.text,
            )
            return vacancies, list(gateway.last_errors)
        finally:
            await gateway.llm_client.aclose()
