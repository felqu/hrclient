import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.domain.models import Application, ApplicationStatus, MatchingProfile, Resume, Vacancy
from app.integrations.resumes import LocalResumeParser, StubResumeStructurer
from app.schemas.contracts import (
    ApplicationDraftCreate,
    ApplicationRead,
    DashboardMetrics,
    MatchingProfileCreate,
    ResumeRead,
    VacancyRead,
    VacancySearch,
)
from app.services.applications import CoverLetterService

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/vacancies/import", status_code=status.HTTP_202_ACCEPTED)
async def import_vacancies(query: VacancySearch) -> dict[str, str]:
    # TODO: inject VacancyService and dispatch import; date range is already a required API contract.
    return {"detail": f"Import scheduled for {query.date_from.isoformat()}..{query.date_to.isoformat()}"}


@router.get("/vacancies", response_model=list[VacancyRead])
async def list_vacancies(session: AsyncSession = Depends(get_session)) -> list[Vacancy]:
    return list((await session.scalars(select(Vacancy).order_by(Vacancy.published_at.desc()).limit(100))).all())


@router.post("/resumes", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...), session: AsyncSession = Depends(get_session)
) -> Resume:
    content = await file.read()
    try:
        raw_text = LocalResumeParser().extract_text(filename=file.filename or "resume.txt", content=content)
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from resume")
    structured_data = await StubResumeStructurer().structure(raw_text)
    resume = Resume(filename=file.filename or "resume", raw_text=raw_text, structured_data=structured_data)
    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    return resume


@router.post("/matching-profiles", status_code=status.HTTP_201_CREATED)
async def create_profile(body: MatchingProfileCreate, session: AsyncSession = Depends(get_session)) -> dict:
    profile = MatchingProfile(name=body.name, rules=body.rules.model_dump(), custom_prompt=body.custom_prompt)
    session.add(profile)
    await session.commit()
    return {"id": str(profile.id), "name": profile.name}


@router.post("/applications/drafts", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
async def create_application_draft(body: ApplicationDraftCreate, session: AsyncSession = Depends(get_session)) -> Application:
    vacancy = await session.get(Vacancy, body.vacancy_id)
    resume = await session.get(Resume, body.resume_id)
    if not vacancy or not resume:
        raise HTTPException(status_code=404, detail="Vacancy or resume not found")
    letter = CoverLetterService().render(body.template, {
        "company": vacancy.company or "команда",
        "position": vacancy.title,
        "top_skills": ", ".join(resume.structured_data.get("skills", [])[:3]),
        "match_score": body.match_score,
    })
    application = Application(vacancy_id=vacancy.id, resume_id=resume.id, cover_letter=letter)
    session.add(application)
    await session.commit()
    await session.refresh(application)
    return application


@router.post("/applications/{application_id}/approve", response_model=ApplicationRead)
async def approve_application(application_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Application:
    application = await session.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.status is not ApplicationStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only drafts can be approved")
    application.status = ApplicationStatus.APPROVED
    # TODO: append ApplicationEvent and enqueue `send_application` atomically with an outbox.
    await session.commit()
    return application


@router.get("/analytics/dashboard", response_model=DashboardMetrics)
async def dashboard(session: AsyncSession = Depends(get_session)) -> DashboardMetrics:
    statuses = (await session.execute(select(Application.status, func.count()).group_by(Application.status))).all()
    counts = {row[0]: row[1] for row in statuses}
    return DashboardMetrics(
        total_sent=counts.get(ApplicationStatus.SENT, 0),
        viewed=counts.get(ApplicationStatus.VIEWED, 0),
        invited=counts.get(ApplicationStatus.INVITED, 0),
        rejected=counts.get(ApplicationStatus.REJECTED, 0),
    )
