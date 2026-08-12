"""Smoke test for the slim Vercel store app (api/store_main.py) with SQLite."""
import os
import sys

os.environ["TESTING"] = "true"
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./smoke-store.db"
os.environ["REDIS_URL"] = ""
os.environ["SECRET_KEY"] = "x" * 64
os.environ["ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="
os.environ["CSRF_SECRET"] = "y" * 32
os.environ["ADMIN_DEFAULT_EMAIL"] = "admin@smoke.test"
os.environ["ADMIN_DEFAULT_PASSWORD"] = "SmokePass!2026"
os.environ["STRICT_BOOTSTRAP"] = "false"
os.environ["INTERNAL_METRICS_TOKEN"] = "test-internal-token"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import asyncio

from starlette.testclient import TestClient

import api.store_main as store
from app.database import engine
from app.models.base import Base


async def main() -> int:
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c))

    with TestClient(store.app) as c:
        # 1. Health
        r = c.get("/health")
        print(f"[1] GET /health -> {r.status_code} {r.json()['status']}")

        # 2. Login as seeded admin (lifespan seeds the admin user)
        r = c.post("/api/v1/auth/login", json={"email": "admin@smoke.test", "password": "SmokePass!2026"})
        print(f"[2] POST /api/v1/auth/login -> {r.status_code}")
        if r.status_code != 200:
            print("   body:", r.text[:200])
            return 1
        token = r.json()["access_token"]
        from app.config import settings as app_settings
        csrf_cookie = c.cookies.get(app_settings.CSRF_COOKIE_NAME, "")
        h = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf_cookie}

        # 3. Create product (authenticated)
        r = c.post("/api/v1/funnel/products", json={
            "name": "Smoke Product", "slug": "smoke-prod",
            "price_amount": "149.00", "currency": "THB",
            "product_type": "prompt_pack",
        }, headers=h)
        print(f"[3] POST /api/v1/funnel/products -> {r.status_code}")
        if r.status_code not in (200, 201):
            print("   body:", r.text[:300])
            return 1
        pid = r.json()["id"]
        org_id = r.json()["organization_id"]

        # 4. Add asset + publish
        r = c.post(f"/api/v1/funnel/products/{pid}/assets", json={
            "asset_type": "content", "title": "Content", "content_body": "# hi",
        }, headers=h)
        print(f"[4] POST asset -> {r.status_code}")
        r = c.post(f"/api/v1/funnel/products/{pid}/publish", headers=h)
        print(f"[5] POST publish -> {r.status_code}")

        # 6. Public product retrieval (was the 401 bug)
        r = c.get(f"/api/v1/funnel/public/products/{org_id}/smoke-prod")
        print(f"[6] GET public product -> {r.status_code} name={r.json().get('name') if r.status_code == 200 else '?'}")

        # 7. Public checkout route (Stripe call will fail without keys — expect clean 4xx/5xx, NOT 401)
        r = c.post(f"/api/v1/funnel/public/products/{pid}/checkout", json={
            "organization_id": org_id,
            "customer_email": "buyer@smoke.test",
            "success_url": "https://x.test/success",
            "cancel_url": "https://x.test/cancel",
        })
        print(f"[7] POST public checkout -> {r.status_code} (401=ยังบั๊ก, อื่น=route ผ่าน)")
        if r.status_code == 401:
            return 1

        # 8. Internal cron bridge (wrong token -> 403)
        r = c.post("/internal/funnel/process-due")
        print(f"[8] POST /internal/funnel/process-due (no token) -> {r.status_code}")
        r = c.post("/internal/funnel/process-due", headers={"X-Internal-Token": "test-internal-token"})
        print(f"[9] POST /internal/funnel/process-due (ok token) -> {r.status_code} {r.text[:120]}")

    print("SMOKE DONE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
