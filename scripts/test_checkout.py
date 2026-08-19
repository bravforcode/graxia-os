"""Live checkout test: create a Stripe Checkout session via the deployed store."""
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.production"))

BASE = "https://graxia-os-funnel.vercel.app"
ORG_ID = "3da2dc2a-6092-443a-9600-ca22aa0553f0"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=90, follow_redirects=True) as c:
        # Warm up (cold start ~8s)
        for i in range(2):
            try:
                r = c.get("/health")
                print(f"health#{i}: {r.status_code}")
            except Exception as exc:
                print(f"health#{i} err: {exc}")
            time.sleep(1)

        r = c.post(
            "/api/v1/auth/login",
            json={
                "email": os.environ["ADMIN_DEFAULT_EMAIL"],
                "password": os.environ["ADMIN_DEFAULT_PASSWORD"],
            },
        )
        print(f"login: {r.status_code}")
        if r.status_code != 200:
            print(r.text[:300])
            return 1
        token = r.json()["access_token"]
        csrf = c.cookies.get("csrf_token", "")
        h = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf, "Cookie": f"csrf_token={csrf}"}

        r = c.get("/api/v1/funnel/products", headers=h)
        prods = r.json() if r.status_code == 200 else []
        prod = next((p for p in prods if p.get("slug", "").startswith("ai-prompt-pack")), None)
        if not prod:
            print(f"product not found ({r.status_code}): {r.text[:200]}")
            return 1
        print(f"using product: {prod['name']} ฿{prod['price_amount']}")

        r = c.post(
            f"/api/v1/funnel/public/products/{prod['id']}/checkout",
            json={
                "organization_id": ORG_ID,
                "customer_email": "buyer@test.local",
                "success_url": f"{BASE}/checkout/success",
                "cancel_url": f"{BASE}/",
            },
        )
        print(f"checkout: {r.status_code}")
        print(r.text[:500])
        if r.status_code == 200:
            data = r.json()
            print("CHECKOUT_URL:", data.get("checkout_url"))
            print("SESSION:", data.get("stripe_session_id"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
