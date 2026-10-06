from __future__ import annotations

import json
import re
from typing import Any

from ..llm_client.llm_client import LLMClient
from ..integrations.models.resume_model import Resume
from ..integrations.models.tg_models import JobVacancy


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