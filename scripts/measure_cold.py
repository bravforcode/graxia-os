"""Measure cold-start components locally (mirrors Vercel bundle)."""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.production"))

REQUIRED = (
    "DATABASE_URL", "SECRET_KEY", "ENCRYPTION_KEY", "CSRF_SECRET", "POSTGRES_PASSWORD",
    "ADMIN_DEFAULT_EMAIL", "ADMIN_DEFAULT_PASSWORD", "RESEND_API_KEY", "INTERNAL_API_KEY",
)
missing = [k for k in REQUIRED if not os.environ.get(k)]
if missing:
    print(f"Missing env vars: {missing}")
    sys.exit(1)

os.environ["APP_ENV"] = "production"
os.environ["FRONTEND_URL"] = "https://graxia-os-funnel.vercel.app"
os.environ["ALLOWED_CORS_ORIGINS"] = "https://graxia-os-funnel.vercel.app"
os.environ["COOKIE_SECURE"] = "false"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

t0 = time.perf_counter()
import api.store_main  # noqa: E402
t1 = time.perf_counter()
print(f"IMPORT: {t1 - t0:.1f}s")

from starlette.testclient import TestClient  # noqa: E402

t2 = time.perf_counter()
with TestClient(api.store_main.app) as c:
    t3 = time.perf_counter()
    print(f"LIFESPAN: {t3 - t2:.1f}s")
    r = c.get("/health")
    t4 = time.perf_counter()
    print(f"HEALTH (warm): {t4 - t3:.2f}s -> {r.status_code}")
