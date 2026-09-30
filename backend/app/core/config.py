from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./hrclient.db"
    redis_url: str = "redis://localhost:6379/0"
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str | None = None
    llm_model: str = "llama3.2"
    llm_temperature: float = 0.2
    hh_client_id: str | None = None
    hh_client_secret: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
