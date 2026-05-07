from pathlib import Path

from app.config import Settings


def test_development_host_rewrite_for_local_runs():
    settings = Settings(
        APP_ENV="development",
        RUNNING_IN_DOCKER=False,
        DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/personal_os",
        REDIS_URL="redis://redis:6379/0",
        CELERY_BROKER_URL="redis://redis:6379/1",
        CELERY_RESULT_BACKEND="redis://redis:6379/2",
    )

    assert "@localhost:5432" in settings.DATABASE_URL
    assert settings.REDIS_URL == "redis://localhost:6379/0"
    assert settings.CELERY_BROKER_URL == "redis://localhost:6379/1"
    assert settings.CELERY_RESULT_BACKEND == "redis://localhost:6379/2"


def test_docker_runs_keep_service_names():
    settings = Settings(
        APP_ENV="development",
        RUNNING_IN_DOCKER=True,
        DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/personal_os",
        REDIS_URL="redis://redis:6379/0",
        CELERY_BROKER_URL="redis://redis:6379/1",
        CELERY_RESULT_BACKEND="redis://redis:6379/2",
    )

    assert "@postgres:5432" in settings.DATABASE_URL
    assert settings.REDIS_URL == "redis://redis:6379/0"


def test_placeholder_detection_helpers():
    settings = Settings(
        GEMINI_API_KEY="your_gemini_api_key_here",
        TELEGRAM_BOT_TOKEN="your_telegram_bot_token_here",
        TELEGRAM_CHAT_ID="your_telegram_chat_id_here",
        SERPAPI_KEY="your_serpapi_key_here",
    )

    assert settings.HAS_REAL_GEMINI_KEY is False
    assert settings.HAS_REAL_TELEGRAM_TOKEN is False
    assert settings.HAS_REAL_TELEGRAM_CHAT_ID is False
    assert settings.HAS_REAL_SERPAPI_KEY is False


def test_settings_env_file_points_to_repo_root():
    env_file = Settings.model_config.get("env_file")

    assert Path(env_file) == Path(__file__).resolve().parents[2] / ".env"


def test_supabase_urls_are_normalized_to_asyncpg():
    settings = Settings(
        DATABASE_URL="postgresql://postgres.project-ref:secret@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
    )

    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert settings.IS_SUPABASE is True
    assert settings.IS_SUPABASE_SESSION_MODE is True
    assert settings.IS_SUPABASE_TRANSACTION_MODE is False


def test_supabase_transaction_mode_is_detected():
    settings = Settings(
        DATABASE_URL="postgres://postgres.project-ref:secret@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
    )

    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert settings.IS_SUPABASE is True
    assert settings.IS_SUPABASE_TRANSACTION_MODE is True
