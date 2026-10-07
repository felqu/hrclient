from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from app.llm_client.llm_client import LLMClient
from app.integrations.models.resume_model import (
    Resume,
    Contact,
    SalaryExpectation,
    Education,
    WorkExperience,
    Project,
    Skill,
    Language,
    WorkFormat,
    EmploymentType,
    ExperienceLevel,
    EducationLevel,
    LanguageProficiency,
)
from app.integrations.models.tg_models import (JobVacancy,
    Company,
    Salary,
    Contacts,
    SourceInfo,
    WorkFormat,
    EmploymentType,
    ExperienceLevel,)


SYSTEM_PROMPT = """Ты — ассистент для составления сопроводительных писем на русском языке.

Правила:
1. Пиши кратко, по-деловому и дружелюбно.
2. Используй только переданные факты о кандидате и вакансии.
3. Не выдумывай опыт, компании, сроки, зарплаты и навыки.
4. Не добавляй тему письма.
5. Не добавляй приветствие и подпись.
6. Верни только текст письма без markdown, без кавычек и без пояснений.
"""


def render_template(template: str | None, context: dict[str, Any]) -> str:
    """
    Безопасная подстановка {placeholder}.

    Пример:
        "Отклик на вакансию: {vacancy_title}"
    """

    if not template:
        return ""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = context.get(key, "")
        if value is None:
            return ""
        return str(value)

    return re.sub(r"{([a-zA-Z0-9_]+)}", _replace, template)


def _clean_llm_text(text: str) -> str:
    text = (text or "").strip()

    # На случай, если модель вернула код-блок.
    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        text = "\n".join(lines)

    return text.strip()


class CoverLetterGenerator:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def generate_body(
        self,
        vacancy: JobVacancy,
        candidate: Resume,
        max_chars: int = 8000,
    ) -> str:
        """
        Генерирует основную часть сопроводительного письма.

        Приветствие и подпись добавляются отдельно в шаблоне письма.
        """

        vacancy_payload = vacancy.model_dump(
            mode="json",
            exclude_none=True,
            exclude={"raw_text"},
        )

        # Полный текст вакансии может быть большим, поэтому передаём усечённую часть.
        vacancy_payload["raw_text_excerpt"] = (vacancy.raw_text or "")[:max_chars]

        candidate_payload = candidate.model_dump(
            mode="json",
            exclude_none=True,
        )

        user_prompt = "\n".join(
            [
                "Составь основную часть сопроводительного письма на основе данных ниже.",
                "",
                "Требования к ответу:",
                "- только русский текст;",
                "- 2-4 абзаца;",
                "- без обращения;",
                "- без подписи;",
                "- без темы письма;",
                "- без markdown;",
                "- не перечисляй контактные данные кандидата;",
                "- опирайся только на переданные факты.",
                "",
                "Данные вакансии:",
                json.dumps(vacancy_payload, ensure_ascii=False, indent=2),
                "",
                "Данные кандидата:",
                json.dumps(candidate_payload, ensure_ascii=False, indent=2),
            ]
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        raw = await self._llm.complete(messages)
        cleaned = _clean_llm_text(raw)

        if cleaned:
            return cleaned

        return self.fallback_body(vacancy, candidate)

    def fallback_body(
        self,
        vacancy: JobVacancy,
        candidate: Resume,
    ) -> str:
        """
        Запасной вариант письма, если LLM недоступен или вернул пустой ответ.
        """

        lines: list[str] = []

        lines.append(
            f"Прошу рассмотреть мою кандидатуру на вакансию «{vacancy.title}»."
        )

        if vacancy.company and vacancy.company.name:
            lines.append(
                f"Меня заинтересовала возможность работать в компании {vacancy.company.name}."
            )

        if candidate.summary:
            lines.append(candidate.summary.strip())

        if candidate.skills:
            key_skills = ", ".join(str(candidate.skills)[:12])
            lines.append(f"Мои ключевые навыки: {key_skills}.")





        return "\n\n".join(lines)

if __name__ == "__main__":
    from datetime import date

    # Предполагается, что модели сохранены в файле job_models.py


    vacancy = JobVacancy(
        title="Python-разработчик",
        company=Company(
            name="ООО «Технологии»",
            website="https://example.com",
            description="Разработка веб-сервисов и внутренних платформ",
        ),
        source=SourceInfo(
            channel_name="IT Вакансии",
            channel_url="https://t.me/it_vacancies",
            original_url="https://t.me/it_vacancies/123",
            message_id="123",
        ),
        work_format=WorkFormat.REMOTE,
        employment_type=EmploymentType.FULL_TIME,
        schedule="5/2, 10:00–19:00",
        location="Москва",
        experience_level=ExperienceLevel.MIDDLE,
        experience_years="1–3 года",
        salary=Salary(
            min_amount=150000,
            max_amount=250000,
            currency="RUB",
            period="month",
            raw_text="от 150 000 до 250 000 ₽ на руки",
        ),
        tasks=[
            "Разработка backend-сервисов на Python",
            "Участие в проектировании архитектуры",
            "Интеграция с внешними API",
        ],
        requirements=[
            "Опыт коммерческой разработки на Python от 2 лет",
            "Знание FastAPI или Django",
            "Опыт работы с PostgreSQL",
        ],
        nice_to_have=[
            "Docker",
            "Kubernetes",
            "CI/CD",
        ],
        technologies=[
            "Python",
            "FastAPI",
            "PostgreSQL",
            "Docker",
        ],
        benefits=[
            "ДМС",
            "Гибкий график",
            "Обучение за счёт компании",
        ],
        contacts=[
            Contacts(
                type="telegram",
                value="@hr_tech",
                raw_text="Писать в Telegram: @hr_tech",
            )
        ],
        raw_text=(
            "Вакансия: Python-разработчик\n"
            "Компания: ООО «Технологии»\n"
            "Формат: удалённо\n"
            "Зарплата: от 150 000 до 250 000 ₽ на руки\n"
            "Требования: Python от 2 лет, FastAPI/Django, PostgreSQL\n"
            "Контакты: @hr_tech"
        ),
        hashtags=["#python", "#backend", "#remote"],
        published_date=date(2026, 10, 7),
        is_active=True,
    )

    resume = Resume(
        full_name="Иванов Иван Иванович",
        headline="Senior Python-разработчик",
        summary="Backend-разработчик с 6-летним опытом. Специализируюсь на "
                "высоконагруженных сервисах, микросервисной архитектуре и API.",
        location="Москва",
        relocation_ready=True,

        work_format=WorkFormat.REMOTE,
        employment_type=EmploymentType.FULL_TIME,
        experience_level=ExperienceLevel.SENIOR,
        total_experience_years=6.5,

        salary_expectation=SalaryExpectation(
            min_amount=300000,
            max_amount=400000,
            currency="RUB",
            period="month",
            raw_text="от 300 000 до 400 000 ₽ на руки",
        ),

        contacts=[
            Contact(type="telegram", value="@ivan_dev", raw_text="TG: @ivan_dev"),
            Contact(type="email", value="ivan@example.com", raw_text="ivan@example.com"),
            Contact(type="phone", value="+7 999 123-45-67", raw_text="+7 999 123-45-67"),
            Contact(type="github", value="https://github.com/ivan-dev"),
            Contact(type="linkedin", value="https://linkedin.com/in/ivan-dev"),
        ],

        skills=[
            Skill(name="Python", level="expert", category="язык"),
            Skill(name="FastAPI", level="advanced", category="фреймворк"),
            Skill(name="Django", level="advanced", category="фреймворк"),
            Skill(name="PostgreSQL", level="advanced", category="СУБД"),
            Skill(name="Docker", level="advanced", category="инструмент"),
            Skill(name="Kubernetes", level="intermediate", category="инструмент"),
            Skill(name="Kafka", level="intermediate", category="инструмент"),
        ],

        languages=[
            Language(name="Русский", proficiency=LanguageProficiency.NATIVE),
            Language(name="Английский", proficiency=LanguageProficiency.C1),
        ],

        work_experience=[
            WorkExperience(
                company="ООО «Технологии»",
                position="Senior Python-разработчик",
                start_date="2022-03",
                end_date="настоящее время",
                location="Москва (удалённо)",
                description="Разработка и поддержка backend-платформы для B2B-сервиса.",
                achievements=[
                    "Снизил время ответа API на 40% за счёт оптимизации запросов",
                    "Внедрил CI/CD, сократив время релиза с 2 часов до 15 минут",
                    "Наставничество над 3 junior-разработчиками",
                ],
                technologies=["Python", "FastAPI", "PostgreSQL", "Kafka", "Docker", "Kubernetes"],
            ),
            WorkExperience(
                company="ООО «Стартап»",
                position="Python-разработчик",
                start_date="2019-06",
                end_date="2022-02",
                location="Санкт-Петербург",
                description="Разработка микросервисов для e-commerce платформы.",
                achievements=[
                    "Спроектировал сервис платежей с пропускной способностью 1000 rps",
                ],
                technologies=["Python", "Django", "Redis", "Celery", "Docker"],
            ),
        ],

        education=[
            Education(
                institution="МГТУ им. Н. Э. Баумана",
                degree="Инженер",
                field_of_study="Информатика и вычислительная техника",
                level=EducationLevel.MASTER,
                start_date="2015-09",
                end_date="2021-06",
                description="Кафедра «Программное обеспечение ЭВМ и информационные технологии»",
            ),
        ],

        projects=[
            Project(
                name="OpenAPI Helper",
                role="Автор",
                description="Библиотека для генерации клиентов по OpenAPI-спецификации.",
                technologies=["Python", "Pydantic", "Typer"],
                link="https://github.com/ivan-dev/openapi-helper",
            ),
            Project(
                name="TaskFlow",
                role="Backend-разработчик",
                description="Сервис управления задачами для небольших команд.",
                technologies=["FastAPI", "PostgreSQL", "React"],
                link="https://taskflow.example.com",
            ),
        ],

        certifications=[
            "AWS Certified Solutions Architect – Associate (2024)",
            "Otus: Highload Architect (2023)",
            "Stepik: Алгоритмы и структуры данных (2021)",
        ],
    )


    llm = LLMClient(os.getenv("ZAI_MODEL"), "zai")
    generator = CoverLetterGenerator(llm)
    test = asyncio.run(generator.generate_body(vacancy=vacancy, candidate=resume))
    print(test)