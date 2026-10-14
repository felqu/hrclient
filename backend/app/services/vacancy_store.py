"""Persistent Telegram vacancies, keyed by channel and message ID."""
from __future__ import annotations

import os
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator

import duckdb

from app.integrations.models.tg_models import JobVacancy
from app.pipeline_log import log_event

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "vacancies.duckdb"
_db_lock = RLock()


def vacancy_id(vacancy: JobVacancy) -> uuid.UUID:
    source = vacancy.source
    channel = (source.channel_name or "") if source else ""
    channel = channel.strip().lower().removeprefix("https://").removeprefix("http://")
    channel = channel.removeprefix("t.me/").removeprefix("s/").lstrip("@").rstrip("/")
    if source and source.message_id:
        key = f"telegram:{channel}:{source.message_id}"
    elif source and source.original_url:
        key = f"telegram:{source.original_url}"
    else:
        key = f"telegram:{channel}:{vacancy.raw_text}"
    return uuid.uuid5(uuid.NAMESPACE_URL, key)


class VacancyStore:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = path if path is not None else os.getenv("VACANCIES_DB_PATH")
        self.path = Path(configured) if configured else DEFAULT_DB_PATH

    @contextmanager
    def _connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        # Each operation owns its connection; serialize writes within the API process.
        with _db_lock:
            log_event("db.open", path=self.path.resolve())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = duckdb.connect(str(self.path))
            try:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS vacancies (
                        id VARCHAR PRIMARY KEY,
                        channel_name VARCHAR,
                        message_id VARCHAR,
                        published_date DATE,
                        title VARCHAR,
                        company VARCHAR,
                        payload JSON NOT NULL,
                        saved_at TIMESTAMPTZ DEFAULT current_timestamp
                    )
                """)
                yield connection
            except Exception:
                log_event("db.failed", level=logging.ERROR, exc_info=True, path=self.path.resolve())
                raise
            finally:
                connection.close()

    def save(self, vacancies: list[JobVacancy]) -> None:
        log_event("db.save.start", path=self.path.resolve(), count=len(vacancies))
        if not vacancies:
            log_event("db.save.done", count=0)
            return
        rows = []
        for vacancy in vacancies:
            source = vacancy.source
            rows.append((
                str(vacancy_id(vacancy)),
                source.channel_name if source else None,
                source.message_id if source else None,
                vacancy.published_date,
                vacancy.title,
                vacancy.company.name if vacancy.company else None,
                vacancy.model_dump_json(),
            ))
        with self._connect() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.executemany("""
                    INSERT INTO vacancies
                        (id, channel_name, message_id, published_date, title, company, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        channel_name = excluded.channel_name,
                        message_id = excluded.message_id,
                        published_date = excluded.published_date,
                        title = excluded.title,
                        company = excluded.company,
                        payload = excluded.payload,
                        saved_at = now()
                """, rows)
                connection.execute("COMMIT")
                log_event("db.save.done", count=len(rows), ids=[row[0] for row in rows])
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def list(self) -> list[JobVacancy]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT payload FROM vacancies
                ORDER BY published_date DESC NULLS LAST, id
            """).fetchall()
        vacancies = [JobVacancy.model_validate_json(row[0]) for row in rows]
        log_event("db.read.done", path=self.path.resolve(), count=len(vacancies))
        return vacancies
