"""
Revenue OS Celery entrypoint — module-level app for `celery -A` CLI.

Usage:
    celery -A graxia.packages.revenue_os.celery.entrypoint:app worker --loglevel=info
    celery -A graxia.packages.revenue_os.celery.entrypoint:app beat --loglevel=info
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .celery_app import create_revenue_os_celery_app


@dataclass
class _EnvSettings:
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    APP_ENV: str = "production"


def _settings() -> _EnvSettings:
    return _EnvSettings(
        CELERY_BROKER_URL=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"),
        CELERY_RESULT_BACKEND=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
        APP_ENV=os.getenv("APP_ENV", "production"),
    )


app = create_revenue_os_celery_app(_settings())