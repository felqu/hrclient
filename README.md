# HR Client — MVP skeleton

Кроссплатформенное приложение для поиска вакансий, оценки соответствия резюме и контролируемых автооткликов. Это именно каркас: HTTP-контракты, модели, интерфейсы интеграций и экран MVP уже есть; предметная логика в отмеченных `TODO` пока не реализована.

## Архитектура

```text
HTML/CSS/JS UI ──HTTP──> FastAPI API ──> PostgreSQL
                       │                 │
                       ├──> Redis <── Celery worker
                       │
                       ├── SourceGateway: HH / Telegram
                       ├── ResumeParser: PDF / DOCX / text
                       ├── MatchingService ──> LLMProvider chain
                       └── ApplicationGateway: HH negotiations
```

### Границы модулей

| Модуль | Ответственность |
| --- | --- |
| `domain` | SQLAlchemy-сущности и общие перечисления |
| `schemas` | публичные Pydantic-контракты API |
| `integrations` | заменяемые адаптеры HH, Telegram и LLM |
| `services` | оркестрация use-cases, правила и транзакции |
| `tasks` | фоновые задачи, retry и rate-limit |
| `api` | тонкие HTTP-роуты |

Frontend — статическая страница на HTML/CSS/JavaScript без сборщика и UI-kit. Она обращается к тем же API-контрактам и может быть позже заменена React-или другим клиентом без изменения backend.

**Поток вакансий:** UI передаёт обязательный диапазон дат → `VacancyService` вызывает нужные `SourceGateway` → нормализованные записи сохраняются в `vacancies`.

**Поток отклика:** скоринг создаёт черновик → пользователь подтверждает → Celery-задача вызывает `ApplicationGateway` с ограничением частоты → событие аудита фиксирует смену статуса.

**LLM:** `LLMProvider` намеренно независим от вендора. `FallbackLLMProvider` обходит цепочку конфигураций, что позволяет переключать OpenAI-compatible, Ollama, llama.cpp и Codex-style endpoint без изменения сервисов.

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

- API: `http://localhost:8000/docs`
- UI: `http://localhost:5173`

Для локальной разработки backend: `cd backend && pip install -e '.[dev]' && uvicorn app.main:app --reload`.
Frontend отдаётся Nginx в Docker Compose; для локального просмотра достаточно открыть `frontend/index.html` или запустить любой статический HTTP-сервер из этой папки.

При первом локальном запуске PostgreSQL выполните `cd backend && alembic upgrade head`; контейнер `api` делает это автоматически. Для проверки backend после установки зависимостей: `cd backend && ruff check app && pytest`.

## Что требует реализации перед production

- OAuth lifecycle и безопасное шифрование токенов HH/Telegram;
- реальные запросы HH, Telethon и LLM, пагинация и дедупликация;
- извлечение текста и LLM-структурирование резюме;
- RBAC/аутентификация, миграции Alembic, observability;
- антиспам-политика, согласие пользователя и соблюдение правил внешних платформ.
