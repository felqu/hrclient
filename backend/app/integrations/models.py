from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from datetime import date
from enum import Enum


class WorkFormat(str, Enum):
    REMOTE = "удалённо"
    HYBRID = "гибрид"
    OFFICE = "офис"
    UNKNOWN = "не указан"

class EmploymentType(str, Enum):
    FULL_TIME = "полная"
    PART_TIME = "частичная"
    CONTRACT = "контракт"
    INTERNSHIP = "стажировка"
    UNKNOWN = "не указана"

class ExperienceLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    LEAD = "lead"
    UNKNOWN = "unknown"


class Company(BaseModel):
    """Информация о компании-работодателе."""
    name: str = Field(..., description="Название компании")
    website: Optional[HttpUrl] = Field(None, description="Сайт компании")
    description: Optional[str] = Field(None, description="Краткое описание деятельности")

class Salary(BaseModel):
    """Информация об оплате труда."""
    min_amount: Optional[int] = Field(None, description="Минимальная сумма (в рублях)")
    max_amount: Optional[int] = Field(None, description="Максимальная сумма (в рублях)")
    currency: str = Field("RUB", description="Валюта")
    period: str = Field("month", description="Период (month, year, hour)")
    raw_text: Optional[str] = Field(None, description="Исходный текст зарплаты, если не удалось распарсить")

class Contact(BaseModel):
    """Контактная информация для отклика."""
    type: str = Field(..., description="Тип контакта (telegram, email, url)")
    value: str = Field(..., description="Значение контакта")
    raw_text: Optional[str] = Field(None, description="Исходная строка контакта")

class SourceInfo(BaseModel):
    """Информация об источнике вакансии."""
    channel_name: Optional[str] = Field(None, description="Название канала/бота")
    channel_url: Optional[HttpUrl] = Field(None, description="Ссылка на канал")
    original_url: Optional[HttpUrl] = Field(None, description="Прямая ссылка на вакансию")
    message_id: Optional[str] = Field(None, description="ID сообщения")

# --- Основная модель вакансии ---

class JobVacancy(BaseModel):
    """
    Структурированное представление вакансии, извлечённое из текстового сообщения.
    Модель покрывает как общие поля, так и специфику IT-вакансий.
    """
    # 1. Идентификация
    title: str = Field(..., description="Название вакансии / должности")
    company: Optional[Company] = Field(None, description="Информация о компании")
    source: Optional[SourceInfo] = Field(None, description="Источник публикации")

    # 2. Условия работы
    work_format: WorkFormat = Field(WorkFormat.UNKNOWN, description="Формат работы")
    employment_type: EmploymentType = Field(EmploymentType.UNKNOWN, description="Тип занятости")
    schedule: Optional[str] = Field(None, description="График работы (например, 5/2, 10:00-18:30)")
    location: Optional[str] = Field(None, description="Местоположение (город/регион)")
    experience_level: ExperienceLevel = Field(ExperienceLevel.UNKNOWN, description="Уровень опыта")
    experience_years: Optional[str] = Field(None, description="Требуемый стаж, например '1–3 года'")

    # 3. Оплата и мотивация
    salary: Optional[Salary] = Field(None, description="Информация об оплате")

    # 4. Содержание вакансии
    tasks: List[str] = Field(default_factory=list, description="Задачи и обязанности")
    requirements: List[str] = Field(default_factory=list, description="Требования к кандидату")
    nice_to_have: List[str] = Field(default_factory=list, description="Желательные навыки (будет плюсом)")
    technologies: List[str] = Field(default_factory=list, description="Ключевые технологии и инструменты")
    benefits: List[str] = Field(default_factory=list, description="Предлагаемые бонусы и условия")

    # 5. Коммуникация
    contacts: List[Contact] = Field(default_factory=list, description="Контакты для отклика")

    # 6. Метаданные
    raw_text: str = Field(..., description="Исходный полный текст сообщения")
    hashtags: List[str] = Field(default_factory=list, description="Хештеги, извлечённые из текста")
    published_date: Optional[date] = Field(None, description="Дата публикации (если указана)")
    is_active: bool = Field(True, description="Флаг, что вакансия актуальна")