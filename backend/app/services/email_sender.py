from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage

import aiosmtplib

from .config import Settings


@dataclass(slots=True)
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass(slots=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str
    attachments: list[Attachment] = field(default_factory=list)


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, email: OutgoingEmail) -> None:
        message = self._build_message(email)

        settings = self.settings

        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_tls_mode == "ssl",
            start_tls=settings.smtp_tls_mode == "starttls",
        )

    def _build_message(self, email: OutgoingEmail) -> EmailMessage:
        settings = self.settings

        from_email = settings.smtp_from_email or settings.smtp_username
        if not from_email:
            raise RuntimeError(
                "Не задан отправитель письма. "
                "Укажите SMTP_FROM_EMAIL или SMTP_USERNAME."
            )

        message = EmailMessage()

        if settings.smtp_from_name:
            message["From"] = f"{settings.smtp_from_name} <{from_email}>"
        else:
            message["From"] = from_email

        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)

        for attachment in email.attachments:
            maintype, subtype = self._parse_content_type(attachment.content_type)

            message.add_attachment(
                attachment.content,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.filename,
            )

        return message

    @staticmethod
    def _parse_content_type(content_type: str) -> tuple[str, str]:
        try:
            maintype, subtype = content_type.split("/", 1)
            subtype = subtype.split(";", 1)[0].strip()

            if not maintype or not subtype:
                raise ValueError

            return maintype, subtype

        except Exception:
            return "application", "octet-stream"