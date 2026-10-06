from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import re
from pathlib import Path

from .config import Settings
from .cover import CoverLetterGenerator, render_template
from .email_sender import Attachment, OutgoingEmail, SmtpEmailSender
from .llm import LLMClient
from .schemas import (
    ApplyRequest,
    ApplyResponse,
    CandidateProfile,
    EmailResult,
)
from .vacancies import JobVacancy


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class ApplyService:
    def __init__(
        self,
        settings: Settings,
        llm: LLMClient,
        sender: SmtpEmailSender,
    ) -> None:
        self.settings = settings
        self.sender = sender
        self.cover_generator = CoverLetterGenerator(llm)

    async def apply(self, request: ApplyRequest) -> ApplyResponse:
        emails = self._extract_email_contacts(request.vacancy)

        if not emails:
            return ApplyResponse(
                vacancy_title=request.vacancy.title,
                results=[
                    EmailResult(
                        contact_value="",
                        status="skipped",
                        detail="В вакансии нет контактов с типом email.",
                    )
                ],
            )

        try:
            candidate = await self._get_candidate(request)
        except Exception as exc:
            return self._error_response(
                request.vacancy,
                emails,
                f"Не удалось получить профиль кандидата: {exc}",
            )

        try:
            attachment = await self._get_resume_attachment(request)
        except Exception as exc:
            return self._error_response(
                request.vacancy,
                emails,
                f"Не удалось получить резюме: {exc}",
            )

        generation_detail: str | None = None

        try:
            generated_letter = await self.cover_generator.generate_body(
                vacancy=request.vacancy,
                candidate=candidate,
                max_chars=self.settings.max_prompt_chars,
            )
        except Exception as exc:
            generated_letter = self.cover_generator.fallback_body(
                vacancy=request.vacancy,
                candidate=candidate,
            )
            generation_detail = f"LLM fallback, ошибка: {exc}"

        context = self._template_context(
            vacancy=request.vacancy,
            candidate=candidate,
            generated_letter=generated_letter,
        )

        subject_template = request.subject_template or self.settings.subject_template
        body_template = request.cover_letter_template or self.settings.body_template

        subject = render_template(subject_template, context)
        body = render_template(body_template, context)

        results: list[EmailResult] = []

        for email_address in emails:
            try:
                email = OutgoingEmail(
                    to=email_address,
                    subject=subject,
                    body=body,
                    attachments=[attachment],
                )

                if request.dry_run:
                    results.append(
                        EmailResult(
                            contact_value=email_address,
                            status="dry_run",
                            detail=generation_detail or "Письмо не отправлялось из-за dry_run.",
                            subject=subject,
                        )
                    )
                else:
                    await self.sender.send(email)
                    results.append(
                        EmailResult(
                            contact_value=email_address,
                            status="sent",
                            detail=generation_detail,
                            subject=subject,
                        )
                    )

            except Exception as exc:
                results.append(
                    EmailResult(
                        contact_value=email_address,
                        status="error",
                        detail=f"Ошибка отправки письма: {exc}",
                        subject=subject,
                    )
                )

        return ApplyResponse(
            vacancy_title=request.vacancy.title,
            results=results,
        )

    # ---------------- helpers ----------------

    def _extract_email_contacts(self, vacancy: JobVacancy) -> list[str]:
        """
        Возвращает уникальные email-адреса из контактов вакансии.
        """

        emails: list[str] = []
        seen: set[str] = set()

        for contact in vacancy.contacts or []:
            contact_type = (contact.type or "").strip().lower()

            if contact_type not in {"email", "e-mail", "mail"}:
                continue

            value = contact.value or ""

            for found_email in EMAIL_RE.findall(value):
                normalized = found_email.lower()

                if normalized not in seen:
                    seen.add(normalized)
                    emails.append(normalized)

        return emails

    async def _get_candidate(self, request: ApplyRequest) -> CandidateProfile:
        """
        Возвращает профиль кандидата из запроса или из файла по умолчанию.
        """

        if request.candidate:
            return request.candidate

        path = self.settings.default_candidate_path

        if path:
            path = Path(path).expanduser()

            if not await asyncio.to_thread(path.is_file):
                raise FileNotFoundError(
                    f"Файл кандидата не найден: {path}"
                )

            raw = await asyncio.to_thread(path.read_text, "utf-8")
            data = json.loads(raw)

            return CandidateProfile.model_validate(data)

        raise ValueError(
            "Профиль кандидата не передан в запросе и не задан "
            "параметр DEFAULT_CANDIDATE_PATH."
        )

    async def _get_resume_attachment(self, request: ApplyRequest) -> Attachment:
        """
        Возвращает резюме из запроса или из файла по умолчанию.
        """

        if request.resume:
            content = base64.b64decode(
                request.resume.content_base64,
                validate=True,
            )

            return Attachment(
                filename=request.resume.filename,
                content=content,
                content_type=request.resume.content_type,
            )

        path = self.settings.default_resume_path

        if path:
            path = Path(path).expanduser()

            if not await asyncio.to_thread(path.is_file):
                raise FileNotFoundError(
                    f"Файл резюме не найден: {path}"
                )

            content = await asyncio.to_thread(path.read_bytes)

            content_type = (
                mimetypes.guess_type(path.name)[0]
                or self.settings.default_resume_content_type
            )

            return Attachment(
                filename=path.name,
                content=content,
                content_type=content_type,
            )

        raise ValueError(
            "Резюме не передано в запросе и не задан параметр DEFAULT_RESUME_PATH."
        )

    def _template_context(
        self,
        vacancy: JobVacancy,
        candidate: CandidateProfile,
        generated_letter: str,
    ) -> dict[str, object]:
        company_name = ""

        if vacancy.company and vacancy.company.name:
            company_name = vacancy.company.name

        company_part = f" в компании {company_name}" if company_name else ""

        contact_lines: list[str] = []

        if candidate.email:
            contact_lines.append(str(candidate.email))

        if candidate.phone:
            contact_lines.append(candidate.phone)

        for name, link in candidate.links.items():
            contact_lines.append(f"{name}: {link}")

        return {
            "vacancy_title": vacancy.title,
            "company_name": company_name,
            "company_part": company_part,
            "generated_letter": generated_letter,
            "candidate_name": candidate.full_name,
            "candidate_contacts": "\n".join(contact_lines),
        }

    def _error_response(
        self,
        vacancy: JobVacancy,
        emails: list[str],
        detail: str,
    ) -> ApplyResponse:
        return ApplyResponse(
            vacancy_title=vacancy.title,
            results=[
                EmailResult(
                    contact_value=email_address,
                    status="error",
                    detail=detail,
                )
                for email_address in emails
            ],
        )