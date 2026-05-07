"""
scripts/smoke_test_imports.py
Validate all package imports resolve correctly without a live DB or Celery broker.

Run from the project root:
    cd "c:\\Users\\menum\\graxia os"
    python scripts/smoke_test_imports.py
"""
import importlib
import os
import sys

# ── Add project root to path so graxia package is importable ─────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Patch env before any module import to prevent fail-fast errors ────────────
_ENV_PATCH = {
    "APP_ENV": "development",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "ADMIN_API_KEY": "test-smoke-key-32chars-padding-ok",
    "STRIPE_WEBHOOK_SECRET": "whsec_test",
    "CELERY_BROKER_URL": "redis://localhost:6379/1",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
    "RESEND_API_KEY": "re_test",
}
for k, v in _ENV_PATCH.items():
    os.environ.setdefault(k, v)

MODULES = [
    # ── Package markers ──────────────────────────────────────────────────────
    "graxia",
    "graxia.packages",
    "graxia.database",

    # ── Revenue OS core ──────────────────────────────────────────────────────
    "graxia.packages.revenue_os",
    "graxia.packages.revenue_os.models",
    "graxia.packages.revenue_os.schemas",
    "graxia.packages.revenue_os.db",
    "graxia.packages.revenue_os.core.db_ops",
    "graxia.packages.revenue_os.services.order_service",

    # ── Celery (import celery_app first so tasks can find it) ─────────────────
    "graxia.packages.revenue_os.celery.celery_app",
    "graxia.packages.revenue_os.celery.tasks.daily_revenue_ops",
    "graxia.packages.revenue_os.celery.tasks.hourly_monitor",
    "graxia.packages.revenue_os.celery.tasks.send_pending_emails",
    "graxia.packages.revenue_os.celery.tasks.campaign_engine",
    "graxia.packages.revenue_os.celery.tasks.weekly_review",

    # ── API middleware & dependencies ─────────────────────────────────────────
    "graxia.services.revenue_os_api.middleware",
    "graxia.services.revenue_os_api.dependencies",

    # ── Routers ───────────────────────────────────────────────────────────────
    "graxia.services.revenue_os_api.routers.system",
    "graxia.services.revenue_os_api.routers.orders",
    "graxia.services.revenue_os_api.routers.ledger",
    "graxia.services.revenue_os_api.routers.refunds",
    "graxia.services.revenue_os_api.routers.entitlements",
    "graxia.services.revenue_os_api.routers.delivery",
    "graxia.services.revenue_os_api.routers.campaigns",
    "graxia.services.revenue_os_api.routers.leads",
    "graxia.services.revenue_os_api.routers.emails",
    "graxia.services.revenue_os_api.routers.approvals",
    "graxia.services.revenue_os_api.routers.incidents",
    "graxia.services.revenue_os_api.routers.dashboard",
    "graxia.services.revenue_os_api.routers.automation",
    "graxia.services.revenue_os_api.routers.checkout",
    "graxia.services.revenue_os_api.router",
]


def run() -> int:
    failures: list = []
    for module in MODULES:
        try:
            importlib.import_module(module)
            print(f"  OK   {module}")
        except Exception as exc:
            print(f"  FAIL {module}: {exc}")
            failures.append((module, exc))

    print()
    if failures:
        print(f"FAILED ({len(failures)}/{len(MODULES)} modules):")
        for mod, err in failures:
            print(f"  - {mod}: {err}")
        return 1

    print(f"All {len(MODULES)} modules imported successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
