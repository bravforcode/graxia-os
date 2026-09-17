"""Fail-closed, no-network preflight for the Revenue OS staging profile."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping


REQUIRED_KEYS = (
    "APP_ENV",
    "NO_LIVE_PAYMENT_MODE",
    "KILL_SWITCH_ALL_EXTERNAL_BETA",
    "DATABASE_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "ADMIN_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
)


class StagingPreflightError(ValueError):
    """Raised when staging is not safe to exercise."""


def _configured(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_staging_environment(env: Mapping[str, str]) -> dict[str, object]:
    """Return a redacted readiness report without contacting providers."""

    checks: dict[str, bool] = {
        key: _configured(env.get(key)) for key in REQUIRED_KEYS
    }
    blockers: list[str] = []
    if env.get("APP_ENV") != "staging":
        blockers.append("APP_ENV must be staging")
    if env.get("NO_LIVE_PAYMENT_MODE", "").lower() != "true":
        blockers.append("NO_LIVE_PAYMENT_MODE must be true")
    if env.get("KILL_SWITCH_ALL_EXTERNAL_BETA", "").lower() != "true":
        blockers.append("KILL_SWITCH_ALL_EXTERNAL_BETA must be true")
    stripe_key = env.get("STRIPE_SECRET_KEY", "")
    if stripe_key and not stripe_key.startswith("sk_test_"):
        blockers.append("STRIPE_SECRET_KEY must be test mode")
    blockers.extend(f"missing {key}" for key, value in checks.items() if not value)
    return {
        "environment": "staging",
        "configured": checks,
        "provider_calls_performed": False,
        "ok": not blockers,
        "blockers": blockers,
    }


def main() -> int:
    report = check_staging_environment(os.environ)
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
