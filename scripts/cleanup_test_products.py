import os

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.production"))

with httpx.Client(base_url="https://graxia-os-funnel.vercel.app", timeout=60, follow_redirects=True) as c:
    r = c.post(
        "/api/v1/auth/login",
        json={
            "email": os.environ["ADMIN_DEFAULT_EMAIL"],
            "password": os.environ["ADMIN_DEFAULT_PASSWORD"],
        },
    )
    token = r.json()["access_token"]
    csrf = c.cookies.get("csrf_token", "")
    h = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf, "Cookie": f"csrf_token={csrf}"}
    r = c.get("/api/v1/funnel/products", headers=h)
    removed = 0
    for p in r.json():
        slug = p.get("slug", "")
        if slug.startswith("prod-test-live") or slug.startswith("live-test"):
            d = c.delete(f"/api/v1/funnel/products/{p['id']}", headers=h)
            print(f"deleted {slug}: {d.status_code}")
            removed += 1
    r = c.get("/api/v1/funnel/products", headers=h)
    print(f"remaining products: {len(r.json())}")
    for p in r.json():
        print(f"  - {p['name']} ฿{p['price_amount']} [{p['status']}]")
