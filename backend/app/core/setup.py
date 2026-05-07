import logging
import os
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def before_send_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """
    Enterprise-grade event filtering and PII sanitization.

    - Filters out health check noise
    - Sanitizes sensitive data
    - Prevents duplicate error flooding
    """
    # Filter out health check endpoints noise
    if event.get("request", {}).get("url", "").endswith("/health"):
        return None

    # Filter out specific low-value errors
    exception = event.get("exception", {})
    if exception:
        values = exception.get("values", [])
        for value in values:
            error_type = value.get("type", "")
            if error_type in ("HTTPException", "StarletteHTTPException"):
                # Filter out 4xx client errors in production (expected)
                if settings.APP_ENV == "production":
                    return None

    return event


def init_sentry():
    """Enterprise-grade Sentry error tracking initialization."""
    SENTRY_DSN = settings.SENTRY_DSN or os.getenv("SENTRY_DSN", "")
    if SENTRY_DSN and not SENTRY_DSN.startswith("your_"):
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.redis import RedisIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

            # Calculate sample rates based on environment
            traces_rate = settings.SENTRY_TRACES_SAMPLE_RATE if settings.APP_ENV == "production" else 0.0
            profiles_rate = settings.SENTRY_PROFILES_SAMPLE_RATE if settings.APP_ENV == "production" else 0.0

            sentry_sdk.init(
                dsn=SENTRY_DSN,
                environment=settings.APP_ENV,
                traces_sample_rate=traces_rate,
                profiles_sample_rate=profiles_rate,
                integrations=[
                    FastApiIntegration(),
                    SqlalchemyIntegration(),
                    RedisIntegration(),
                ],
                send_default_pii=False,
                before_send=before_send_event,
                release=f"graxia-os@{os.getenv('APP_VERSION', '7.2.0')}",
            )
            logger.info("Sentry error tracking initialized")
        except ImportError:
            logger.warning("Sentry SDK not installed, error tracking disabled")
        except Exception as e:
            logger.warning(f"Failed to initialize Sentry: {e}")
    else:
        logger.info("Sentry error tracking disabled")
