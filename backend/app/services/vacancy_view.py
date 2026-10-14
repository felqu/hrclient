"""Filtering and table rows shared by the UI and tests."""
from __future__ import annotations

from datetime import date

from app.integrations.models.tg_models import JobVacancy


def filter_vacancies(
    vacancies: list[JobVacancy], *, text: str = "", channels: list[str] | None = None,
    work_formats: list[str] | None = None, experience: list[str] | None = None,
    date_from: date | None = None, date_to: date | None = None, include_undated: bool = True,
) -> list[JobVacancy]:
    result = []
    for vacancy in vacancies:
        channel = vacancy.source.channel_name if vacancy.source else None
        if channels and channel not in channels:
            continue
        if work_formats and vacancy.work_format.value not in work_formats:
            continue
        if experience and vacancy.experience_level.value not in experience:
            continue
        if vacancy.published_date is None:
            if not include_undated:
                continue
        elif ((date_from and vacancy.published_date < date_from)
              or (date_to and vacancy.published_date > date_to)):
            continue
        haystack = " ".join([vacancy.title, vacancy.company.name if vacancy.company else "",
                             vacancy.raw_text, " ".join(vacancy.technologies)])
        if text.strip() and text.strip().casefold() not in haystack.casefold():
            continue
        result.append(vacancy)
    return result


def vacancy_rows(vacancies: list[JobVacancy]) -> list[dict]:
    rows = []
    for vacancy in vacancies:
        salary = vacancy.salary
        pay = "Не указана"
        if salary:
            amounts = []
            if salary.min_amount is not None:
                amounts.append(f"от {salary.min_amount:,}".replace(",", " "))
            if salary.max_amount is not None:
                amounts.append(f"до {salary.max_amount:,}".replace(",", " "))
            pay = f"{' · '.join(amounts)} {salary.currency} / {salary.period}" if amounts else (salary.raw_text or "Не указана")
        source = vacancy.source
        rows.append({
            "Вакансия": vacancy.title, "Компания": vacancy.company.name if vacancy.company else "—",
            "Канал": source.channel_name if source else "—", "Дата": vacancy.published_date,
            "Формат": vacancy.work_format.value, "Уровень": vacancy.experience_level.value,
            "Город": vacancy.location or "—", "Зарплата": pay,
            "Технологии": ", ".join(vacancy.technologies),
            "Ссылка": str(source.original_url or source.channel_url or "") if source else "",
        })
    return rows
