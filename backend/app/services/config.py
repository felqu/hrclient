from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_BODY_TEMPLATE = """Здравствуйте!

Направляю отклик на вакансию «{vacancy_title}»{company_part}.

{generated_letter}

С уважением,
{candidate_name}
{candidate_contacts}
"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # LLM
    llm_provider: Literal["zai", "nvidia"] = "zai"
    llm_model: str | None = None
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.6

    # SMTP
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_tls_mode: Literal["ssl", "starttls", "plain"] = "starttls"
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "Apply Service"

    # Резюме и профиль кандидата по умолчанию
    default_resume_path: Path | None = None
    default_resume_content_type: str = "application/pdf"
    default_candidate_path: Path | None = None

    # Шаблоны письма
    subject_template: str = "Отклик на вакансию: {vacancy_title}"
    body_template: str = DEFAULT_BODY_TEMPLATE

    # Ограничения для prompt
    max_prompt_chars: int = 8000