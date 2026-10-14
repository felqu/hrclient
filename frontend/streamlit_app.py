"""Run from the project root: python -m streamlit run frontend/streamlit_app.py."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import pandas as pd
import streamlit as st

from app.pipeline_log import DEFAULT_LOG_PATH, log_event, pipeline_run
from app.services.parse_jobs import ParseJobManager, ParseSettings
from app.services.vacancy_export import vacancies_xlsx
from app.services.vacancy_store import VacancyStore
from app.services.vacancy_view import filter_vacancies, vacancy_rows

st.set_page_config(page_title="HR Client · Вакансии", page_icon="🔎", layout="wide")


@st.cache_resource
def job_manager() -> ParseJobManager:
    return ParseJobManager()


def event_label(event: dict) -> str:
    names = {
        "parse.start": "Запуск парсинга", "channel.fetch.start": "Получение сообщений",
        "channel.fetch.done": "Сообщения получены", "message.received": "Получено сообщение",
        "llm.request": "Запрос к LLM", "llm.response": "Ответ LLM",
        "llm.failed": "Ошибка LLM", "llm.invalid_response": "Некорректный ответ LLM",
        "llm.invalid_json": "Некорректный JSON", "message.skipped": "Сообщение пропущено",
        "message.processed": "Сообщение обработано", "vacancy.parsed": "Вакансия извлечена",
        "vacancy.accepted": "Вакансия найдена", "channel.done": "Канал обработан",
        "channel.fetch.failed": "Ошибка канала", "db.save.start": "Сохранение в базу",
        "db.save.done": "Вакансии сохранены", "parse.done": "Запуск завершён",
        "parse.failed": "Ошибка парсинга", "parse.cancelled": "Парсинг остановлен",
    }
    details = event["details"]
    suffix = details.get("channel", "")
    if details.get("message_id") is not None:
        suffix += f" · сообщение {details['message_id']}"
    if details.get("reason"):
        suffix += f" · {details['reason']}"
    return f"{names.get(event['event'], event['event'])} {suffix}".strip()


manager = job_manager()
history = manager.history()
active_id = manager.active_id()
if "current_job" not in st.session_state and history:
    st.session_state.current_job = active_id or history[0]["id"]

with st.sidebar:
    st.title("HR Client")
    st.caption("Telegram → LLM → вакансии")
    st.divider()
    with st.form("parse_settings"):
        st.subheader("Новый парсинг")
        chats_text = st.text_area("Каналы", value=os.getenv("TG_DEFAULT_CHATS", ""),
                                  placeholder="@python_vakansii_jobs\n@devjobs", height=130)
        st.caption("По одному в строке или через запятую")
        today = date.today()
        start = st.date_input("Дата от", value=today - timedelta(days=7))
        end = st.date_input("Дата до", value=today)
        backend = st.selectbox("Парсер Telegram", ["tg_parser", "private_tg_parser"],
                               format_func=lambda value: "Публичные каналы" if value == "tg_parser"
                               else "Telethon · с авторизацией",
                               help="Для Telethon нужна уже авторизованная сессия Telegram.")
        text_filter = st.text_input("Слова в тексте", placeholder="Python, аналитик…")
        maximum = st.number_input("Сообщений на канал", min_value=1, max_value=10_000,
                                   value=500, step=50)
        submitted = st.form_submit_button("Запустить парсинг", type="primary", width="stretch",
                                          disabled=active_id is not None)
    if submitted:
        try:
            chats = list(dict.fromkeys(value.strip() for value in re.split(r"[\n,;]+", chats_text)
                                       if value.strip()))
            settings = ParseSettings(chats, start, end, backend, text_filter.strip() or None, int(maximum))
            st.session_state.current_job = manager.start(settings)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if active_id:
        st.info("Парсинг идёт в фоне. Можно просматривать и фильтровать вакансии.")
    with st.expander("Подключение LLM"):
        st.caption("Параметры берутся из .env")
        st.write("Модель:", os.getenv("NVIDIA_DEEPSEEK") or "Не задана")
        st.caption("Для llama.cpp можно указать локальный адрес в NVIDIA_BASE_URL.")

st.title("Вакансии и парсинг")
st.caption("Сохранённые вакансии, прогресс обработки и результаты работы LLM в одном месте")


@st.fragment(run_every=1 if active_id else None)
def parsing_progress() -> None:
    job_id = st.session_state.get("current_job")
    snapshot = manager.snapshot(job_id) if job_id else None
    if not snapshot:
        st.info("Задайте каналы слева и запустите парсинг. Сохранённые вакансии доступны ниже.")
        return
    with st.container(border=True):
        heading, action = st.columns([4, 1])
        heading.subheader("Прогресс парсинга")
        if action.button("Остановить", disabled=snapshot["terminal"] or snapshot["state"] == "stopping",
                         width="stretch"):
            manager.stop(job_id)
            st.rerun()
        st.progress(snapshot["progress"], text=snapshot["stage"])
        columns = st.columns(4)
        for column, label, field in zip(columns, ["Получено сообщений", "Обработано", "Найдено вакансий", "Ошибки LLM"],
                                         ["received", "processed", "found", "llm_errors"]):
            column.metric(label, snapshot[field])
        st.caption(f"Каналы: {snapshot['completed_channels']}/{snapshot['total_channels']} · "
                   f"Запросов к LLM: {snapshot['llm_requests']} · Пропущено: {snapshot['skipped']} · "
                   f"Сохранено: {snapshot['saved']} · Время: {snapshot['elapsed']:.1f} с")
        if snapshot["state"] == "stopping":
            st.warning("Остановка после текущего сетевого запроса. Найденные вакансии будут сохранены.")
        elif snapshot["state"] == "completed":
            st.success(f"Готово. Сохранено вакансий: {snapshot['saved']}.")
        elif snapshot["state"] == "cancelled":
            st.warning(f"Парсинг остановлен. Сохранено вакансий: {snapshot['saved']}.")
        elif snapshot["state"] in {"failed", "completed_with_errors"}:
            st.warning(f"{snapshot['stage']}. Сохранено вакансий: {snapshot['saved']}.")
        if snapshot["errors"]:
            with st.expander(f"Ошибки ({len(snapshot['errors'])})"):
                for error in snapshot["errors"]:
                    st.error(error)
        with st.expander("Последние события", expanded=not snapshot["terminal"]):
            st.dataframe(pd.DataFrame([
                {"Время": event["time"], "Событие": event_label(event)}
                for event in snapshot["events"][-8:]
            ]), hide_index=True, width="stretch")
    if snapshot["terminal"] and st.session_state.get("synced_job") != job_id:
        st.session_state.synced_job = job_id
        st.rerun()


parsing_progress()
vacancies_tab, journal_tab = st.tabs(["Сохранённые вакансии", "Журнал парсинга"])

with vacancies_tab:
    try:
        vacancies = VacancyStore().list()
    except Exception as exc:
        st.error(f"Не удалось прочитать базу вакансий: {exc}")
        vacancies = []
    totals = st.columns(3)
    totals[0].metric("В базе", len(vacancies))
    totals[1].metric("Каналов", len({v.source.channel_name for v in vacancies if v.source}))
    totals[2].metric("С указанной зарплатой", sum(v.salary is not None for v in vacancies))
    if st.button("Обновить вакансии"):
        st.rerun()
    with st.container(border=True):
        query = st.text_input("Поиск по названию, компании, технологиям и тексту", key="vacancy_search")
        filters = st.columns(3)
        channels = filters[0].multiselect("Каналы", sorted({v.source.channel_name for v in vacancies
                                                           if v.source and v.source.channel_name}))
        formats = filters[1].multiselect("Формат работы", sorted({v.work_format.value for v in vacancies}))
        levels = filters[2].multiselect("Уровень опыта", sorted({v.experience_level.value for v in vacancies}))
        with st.expander("Дата публикации"):
            dates = [v.published_date for v in vacancies if v.published_date]
            date_range = st.date_input("Диапазон дат", value=(min(dates), max(dates)) if dates else (),
                                       key="vacancy_dates")
            include_undated = st.checkbox("Включать вакансии без даты", value=True)
        date_from = date_range[0] if len(date_range) >= 1 else None
        date_to = date_range[1] if len(date_range) == 2 else None
        filtered = filter_vacancies(vacancies, text=query, channels=channels, work_formats=formats,
                                   experience=levels, date_from=date_from, date_to=date_to,
                                   include_undated=include_undated)
    st.caption(f"Показано {len(filtered)} из {len(vacancies)} вакансий")
    export_signature = hashlib.sha256("".join(v.model_dump_json() for v in filtered).encode()).hexdigest()
    if st.session_state.get("export_signature") != export_signature:
        st.session_state.pop("export_bytes", None)
    prepare, download = st.columns([1, 3])
    if prepare.button("Подготовить XLSX", disabled=not filtered):
        try:
            with st.spinner("Создаём XLSX…"), pipeline_run():
                log_event("export.start", count=len(filtered))
                content = vacancies_xlsx(filtered)
                log_event("export.done", count=len(filtered), bytes=len(content))
            st.session_state.export_bytes = content
            st.session_state.export_signature = export_signature
        except Exception as exc:
            log_event("export.failed", error=str(exc))
            st.error(f"Не удалось создать XLSX: {exc}")
    if "export_bytes" in st.session_state:
        download.download_button("Скачать XLSX", data=st.session_state.export_bytes,
                                 file_name=f"vacancies-{date.today():%Y-%m-%d}.xlsx",
                                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 on_click="ignore")
    else:
        download.caption("Экспортируются вакансии с учётом выбранных фильтров")
    if filtered:
        table = st.dataframe(pd.DataFrame(vacancy_rows(filtered)), hide_index=True, width="stretch",
                             height=380, on_select="rerun", selection_mode="single-row",
                             column_config={"Ссылка": st.column_config.LinkColumn("Ссылка", display_text="Открыть")})
        indexes = table.selection.rows
        index = indexes[0] if indexes and indexes[0] < len(filtered) else 0
        vacancy = filtered[index]
        st.subheader(vacancy.title)
        st.caption("Выберите строку таблицы, чтобы открыть другую вакансию")
        detail, raw, structured = st.tabs(["Условия и требования", "Исходное сообщение", "Все поля"])
        with detail:
            st.write("**Компания:**", vacancy.company.name if vacancy.company else "Не указана")
            st.write("**Формат:**", vacancy.work_format.value, "·", vacancy.employment_type.value)
            st.write("**Зарплата:**", vacancy_rows([vacancy])[0]["Зарплата"])
            left, right = st.columns(2)
            left.write("**Задачи**")
            for task in vacancy.tasks:
                left.write(f"• {task}")
            right.write("**Требования**")
            for requirement in vacancy.requirements:
                right.write(f"• {requirement}")
            st.write("**Технологии:**", ", ".join(vacancy.technologies) or "Не указаны")
            for contact in vacancy.contacts:
                st.write(f"{contact.type}: {contact.value}")
            source = vacancy.source
            if source and (source.original_url or source.channel_url):
                st.link_button("Открыть публикацию в Telegram", str(source.original_url or source.channel_url))
        with raw:
            st.text(vacancy.raw_text)
        with structured:
            st.json(vacancy.model_dump(mode="json"))
    else:
        st.info("Вакансий по выбранным условиям нет. Измените фильтры или запустите парсинг.")

with journal_tab:
    history = manager.history()
    if history:
        lookup = {entry["id"]: entry for entry in history}
        selected_id = st.selectbox("Запуск", list(lookup), format_func=lambda value:
                                  f"{value} · {', '.join(lookup[value]['chats'])} · {lookup[value]['state']}")
        snapshot = lookup[selected_id]
        st.caption("История последних 20 запусков хранится до перезапуска приложения")
        st.caption("Здесь доступны последние 300 событий запуска. Полная история записывается в файловый лог.")
        st.button("Обновить журнал")
        events = snapshot["events"]
        if events:
            selected_event = st.selectbox("Событие", list(range(len(events))), index=len(events) - 1,
                                          format_func=lambda value: f"{events[value]['time']} · {event_label(events[value])}")
            st.json(events[selected_event]["details"])
            st.download_button("Скачать журнал запуска", data="\n".join(json.dumps(event, ensure_ascii=False,
                                default=str) for event in events), file_name=f"parse-{selected_id}.jsonl",
                                mime="application/x-ndjson", on_click="ignore")
    else:
        st.info("После запуска здесь появятся сообщения Telegram, ответы LLM и результаты обработки.")
    with st.expander("Последние строки файлового лога"):
        log_path = Path(os.getenv("PARSE_LOG_PATH") or DEFAULT_LOG_PATH)
        if log_path.is_file():
            with log_path.open("rb") as file:
                file.seek(max(0, log_path.stat().st_size - 80_000))
                tail = file.read().decode("utf-8", errors="replace")
            st.code("\n".join(tail.splitlines()[-40:]), language="text")
        else:
            st.caption("Лог появится после первого запуска")
