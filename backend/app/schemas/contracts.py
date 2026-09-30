import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.models import ApplicationStatus, VacancySource


class DateRange(BaseModel):
    date_from: datetime
    date_to: datetime


class VacancySearch(DateRange):
    text: str | None = None
    sources: list[VacancySource] = Field(default_factory=lambda: list(VacancySource))
    telegram_chats: list[str] = Field(default_factory=list)


class VacancyRead(BaseModel):
    id: uuid.UUID
    source: VacancySource
    title: str
    company: str | None
    description: str
    url: str
    published_at: datetime

    model_config = {"from_attributes": True}


class ResumeRead(BaseModel):
    id: uuid.UUID
    filename: str
    structured_data: dict

    model_config = {"from_attributes": True}


class MatchingRules(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_score: int = Field(default=70, ge=0, le=100)
    weights: dict[str, float] = Field(
        default_factory=lambda: {"stack": 0.4, "experience": 0.3, "salary": 0.15, "location": 0.15}
    )
    company_blacklist: list[str] = Field(default_factory=list)
    company_whitelist: list[str] = Field(default_factory=list)
    keyword_blacklist: list[str] = Field(default_factory=list)


class MatchingProfileCreate(BaseModel):
    name: str
    rules: MatchingRules = Field(default_factory=MatchingRules)
    custom_prompt: str | None = None


class MatchRequest(BaseModel):
    resume_id: uuid.UUID
    profile_id: uuid.UUID


class MatchResult(BaseModel):
    vacancy_id: uuid.UUID
    score: float = Field(ge=0, le=100)
    rationale: str
    breakdown: dict[str, float]


class ApplicationDraftCreate(BaseModel):
    vacancy_id: uuid.UUID
    resume_id: uuid.UUID
    match_score: float = Field(ge=0, le=100)
    template: str = "Здравствуйте, {company}! Меня заинтересовала позиция {position}. {top_skills}"


class ApplicationRead(BaseModel):
    id: uuid.UUID
    vacancy_id: uuid.UUID
    status: ApplicationStatus
    cover_letter: str

    model_config = {"from_attributes": True}


class DashboardMetrics(BaseModel):
    total_sent: int = 0
    viewed: int = 0
    invited: int = 0
    rejected: int = 0
    average_match_score: float = 0
