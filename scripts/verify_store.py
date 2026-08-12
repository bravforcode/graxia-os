import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.production"))

BASE = "https://graxia-os-funnel.vercel.app"

with httpx.Client(base_url=BASE, timeout=60, follow_redirects=True) as c:
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
    prods = r.json() if r.status_code == 200 else []
    print(f"products in store: {len(prods)}")
    for p in prods:
        print(f"  - {p['name']} | ฿{p['price_amount']} | status={p['status']} | slug={p['slug']}")
        if p["status"] == "published":
            pr = c.get(f"/api/v1/funnel/public/products/{p['organization_id']}/{p['slug']}")
            print(f"      public check -> {pr.status_code}")

    r = c.get("/api/v1/funnel/analytics/summary", headers=h)
    print(f"analytics summary -> {r.status_code} {r.text[:200]}" if r.status_code == 200 else f"analytics -> {r.status_code}")
