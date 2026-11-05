import sys

from sqlalchemy.pool import NullPool

from app import database
from app.config import settings

POSTGRES_URL = "postgresql+asyncpg://graxia:graxia@localhost:5432/graxia"


def _use_postgres(monkeypatch, argv):
    monkeypatch.setattr(settings, "DATABASE_URL", POSTGRES_URL)
    monkeypatch.delenv("DB_POOL_CLASS", raising=False)
    monkeypatch.setattr(sys, "argv", argv)


def test_celery_process_uses_null_pool(monkeypatch):
    _use_postgres(monkeypatch, ["celery", "-A", "app.tasks.celery_app", "worker"])

    engine = database.create_engine_with_retry()

    assert isinstance(engine.pool, NullPool)


def test_db_pool_class_env_forces_null_pool(monkeypatch):
    _use_postgres(monkeypatch, ["uvicorn", "app.main:app"])
    monkeypatch.setenv("DB_POOL_CLASS", "NullPool")

    engine = database.create_engine_with_retry()

    assert isinstance(engine.pool, NullPool)


def test_web_process_keeps_pooled_connections(monkeypatch):
    _use_postgres(monkeypatch, ["uvicorn", "app.main:app"])

    engine = database.create_engine_with_retry()

    assert not isinstance(engine.pool, NullPool)
    assert engine.pool.size() == settings.DB_POOL_SIZE
