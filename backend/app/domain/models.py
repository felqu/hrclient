import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class VacancySource(str, enum.Enum):
    HH = "hh"
    TELEGRAM = "telegram"


class ApplicationStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    QUEUED = "queued"
    SENT = "sent"
    VIEWED = "viewed"
    INVITED = "invited"
    REJECTED = "rejected"
    FAILED = "failed"


class TimestampedIdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Resume(TimestampedIdMixin, Base):
    __tablename__ = "resumes"
    filename: Mapped[str] = mapped_column(String(255))
    raw_text: Mapped[str] = mapped_column(Text)
    structured_data: Mapped[dict] = mapped_column(JSONB, default=dict)


class MatchingProfile(TimestampedIdMixin, Base):
    __tablename__ = "matching_profiles"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)


class Vacancy(TimestampedIdMixin, Base):
    __tablename__ = "vacancies"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_vacancy_source_external"),)
    source: Mapped[VacancySource] = mapped_column(Enum(VacancySource))
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class Match(TimestampedIdMixin, Base):
    __tablename__ = "matches"
    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id"))
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id"))
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matching_profiles.id"))
    score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)


class Application(TimestampedIdMixin, Base):
    __tablename__ = "applications"
    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id"))
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id"))
    status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus), default=ApplicationStatus.DRAFT)
    cover_letter: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ApplicationEvent(TimestampedIdMixin, Base):
    __tablename__ = "application_events"
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"))
    status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
