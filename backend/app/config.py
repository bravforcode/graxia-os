import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://personal_os:changeme@postgres:5432/personal_os"
    POSTGRES_DB: str = "personal_os"
    POSTGRES_USER: str = "personal_os"
    POSTGRES_PASSWORD: str = "changeme"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # AI — Gemini
    GEMINI_API_KEY: str = ""
    DEFAULT_MODEL: str = "gemini-2.0-flash"
    FAST_MODEL: str = "gemini-2.0-flash-lite"
    GEMINI_DAILY_REQUEST_LIMIT: int = 1400

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # SerpAPI
    SERPAPI_KEY: str = ""

    # Identity
    IDENTITY_PATH: str = "/identity/profile.yaml"

    # Cost controls
    MAX_DAILY_REQUESTS: int = 1400
    MAX_DAILY_AI_COST_USD: float = 2.00
    MAX_MONTHLY_AI_COST_USD: float = 30.00
    MAX_OUTREACH_PER_DAY: int = 5
    MAX_PENDING_APPROVALS: int = 10

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
