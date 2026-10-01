from pydantic import BaseModel, Field, HttpUrl, EmailStr
from typing import List, Optional
from datetime import date
from enum import Enum


class WorkFormat(str, Enum):
    REMOTE = "удалённо"
    HYBRID = "гибрид"
    OFFICE = "офис"
    ANY = "любой"

class EmploymentType(str, Enum):
    FULL = "полная"
    PART = "частичная"
    CONTRACT = "контракт"
    PROJECT = "проектная"
    INTERNSHIP = "стажировка"

class ExperienceLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"

class EducationLevel(str, Enum):
    SECONDARY = "среднее"
    BACHELOR = "бакалавр"
    MASTER = "магистр"
    PHD = "кандидат наук"
    COURSES = "курсы"

class LanguageProficiency(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    NATIVE = "родной"


class Contact(BaseModel):
    """Контактная информация кандидата."""
    type: str = Field(..., description="Тип контакта: telegram, email, phone, linkedin, github и т.п.")
    value: str = Field(..., description="Значение контакта")
    raw_text: Optional[str] = Field(None, description="Исходная строка контакта")

class SalaryExpectation(BaseModel):
    """Ожидания по заработной плате."""
    min_amount: Optional[int] = Field(None, description="Минимальная сумма")
    max_amount: Optional[int] = Field(None, description="Максимальная сумма")
    currency: str = Field("RUB", description="Валюта")
    period: str = Field("month", description="Период: month, year, hour")
    raw_text: Optional[str] = Field(None, description="Исходный текст ожиданий")

class Education(BaseModel):
    """Запись об образовании."""
    institution: str = Field(..., description="Название учебного заведения")
    degree: Optional[str] = Field(None, description="Степень/специальность")
    field_of_study: Optional[str] = Field(None, description="Направление подготовки")
    level: Optional[EducationLevel] = Field(None, description="Уровень образования")
    start_date: Optional[str] = Field(None, description="Дата начала (текстом или в формате YYYY-MM)")
    end_date: Optional[str] = Field(None, description="Дата окончания (текстом или YYYY-MM)")
    description: Optional[str] = Field(None, description="Дополнительное описание")

class WorkExperience(BaseModel):
    """Запись об опыте работы."""
    company: str = Field(..., description="Название компании")
    position: str = Field(..., description="Должность")
    start_date: Optional[str] = Field(None, description="Дата начала")
    end_date: Optional[str] = Field(None, description="Дата окончания (или 'настоящее время')")
    location: Optional[str] = Field(None, description="Город/регион")
    description: Optional[str] = Field(None, description="Описание обязанностей")
    achievements: List[str] = Field(default_factory=list, description="Ключевые достижения")
    technologies: List[str] = Field(default_factory=list, description="Использованные технологии")

class Project(BaseModel):
    """Информация о проекте."""
    name: str = Field(..., description="Название проекта")
    role: Optional[str] = Field(None, description="Роль в проекте")
    description: Optional[str] = Field(None, description="Описание проекта")
    technologies: List[str] = Field(default_factory=list, description="Технологии проекта")
    link: Optional[HttpUrl] = Field(None, description="Ссылка на проект")

class Skill(BaseModel):
    """Навык кандидата."""
    name: str = Field(..., description="Название навыка")
    level: Optional[str] = Field(None, description="Уровень владения (если указан)")
    category: Optional[str] = Field(None, description="Категория: язык, фреймворк, инструмент и т.п.")

class Language(BaseModel):
    """Владение языком."""
    name: str = Field(..., description="Название языка")
    proficiency: Optional[LanguageProficiency] = Field(None, description="Уровень владения")



class Resume(BaseModel):
    """
    Структурированное представление резюме кандидата.
    """
    # 1. Личные данные
    full_name: Optional[str] = Field(None, description="ФИО кандидата")
    headline: Optional[str] = Field(None, description="Желаемая должность / заголовок")
    summary: Optional[str] = Field(None, description="О себе / краткое резюме")
    location: Optional[str] = Field(None, description="Город проживания")
    relocation_ready: bool = Field(False, description="Готовность к переезду")

    # 2. Условия работы
    work_format: WorkFormat = Field(WorkFormat.ANY, description="Предпочитаемый формат работы")
    employment_type: EmploymentType = Field(EmploymentType.FULL, description="Тип занятости")
    experience_level: ExperienceLevel = Field(ExperienceLevel.UNKNOWN, description="Уровень опыта")
    total_experience_years: Optional[float] = Field(None, description="Общий стаж в годах")

    # 3. Оплата
    salary_expectation: Optional[SalaryExpectation] = Field(None, description="Ожидания по зарплате")

    # 4. Контакты
    contacts: List[Contact] = Field(default_factory=list, description="Контактные данные")

    # 5. Навыки и языки
    skills: List[Skill] = Field(default_factory=list, description="Профессиональные навыки")
    languages: List[Language] = Field(default_factory=list, description="Владение языками")

    # 6. Опыт и образование
    work_experience: List[WorkExperience] = Field(default_factory=list, description="Опыт работы")
    education: List[Education] = Field(default_factory=list, description="Образование")
    projects: List[Project] = Field(default_factory=list, description="Проекты")
    certifications: List[str] = Field(default_factory=list, description="Сертификаты и курсы")

