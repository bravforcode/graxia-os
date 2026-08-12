"""Simulate a real Stripe webhook (checkout.session.completed) with a VALID
signature to verify the full money pipeline: webhook -> order -> delivery.

No real payment needed: Stripe would deliver an event with the same shape
for an actual purchase.
"""
import json
import os
import sys
import time

import httpx
import stripe
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.production"))

BASE = "https://graxia-os-funnel.vercel.app"
ORG_ID = "3da2dc2a-6092-443a-9600-ca22aa0553f0"
PRODUCT_ID = "ef010cd2-055a-48fb-a162-04918e3ef00e"  # AI Prompt Pack
CHECKOUT_ID = "fad4bb09-f9f4-494e-8624-4a51c9d61f8c"  # session created in the live test


def main() -> int:
    whsec = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not whsec:
        print("MISSING STRIPE_WEBHOOK_SECRET")
        return 1

    # 1. Build the event payload exactly as Stripe would send it
    payload = json.dumps(
        {
            "id": "evt_sim_completed_001",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": f"cs_live_{'a1weKW18QIbHB2RY2KhllpYxBksJQKDrwJjKgwyEpbTUyMpHvAzBRjo6Qv'[:20]}",
                    "object": "checkout.session",
                    "payment_status": "paid",
                    "customer_email": "buyer@test.local",
                    "amount_total": 14900,
                    "currency": "thb",
                    "metadata": {
                        "organization_id": ORG_ID,
                        "product_id": PRODUCT_ID,
                        "funnel_checkout_session_id": CHECKOUT_ID,
                    },
                }
            },
        }
    ).encode()

    # 2. Sign it with the real webhook secret (Stripe scheme: t=<ts>,v1=<hmac>)
    import hashlib
    import hmac as hmac_mod

    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload
    sig_v1 = hmac_mod.new(whsec.encode(), signed_payload, hashlib.sha256).hexdigest()
    sig = f"t={timestamp},v1={sig_v1}"
    print(f"webhook signature: {sig[:60]}...")

    # 3. POST to the deployed webhook endpoint
    with httpx.Client(base_url=BASE, timeout=60, follow_redirects=True) as c:
        r = c.post(
            "/api/v1/funnel/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
        )
        print(f"webhook POST -> {r.status_code} {r.text[:200]}")

        # 4. Check the order was created
        login = c.post(
            "/api/v1/auth/login",
            json={
                "email": os.environ["ADMIN_DEFAULT_EMAIL"],
                "password": os.environ["ADMIN_DEFAULT_PASSWORD"],
            },
        )
        if login.status_code != 200:
            print(f"login failed: {login.status_code}")
            return 1
        token = login.json()["access_token"]
        csrf = c.cookies.get("csrf_token", "")
        h = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf, "Cookie": f"csrf_token={csrf}"}

        r = c.get("/api/v1/funnel/orders", headers=h)
        print(f"orders list -> {r.status_code}")
        if r.status_code == 200:
            orders = r.json() if isinstance(r.json(), list) else r.json().get("orders", r.json().get("items", []))
            if orders:
                latest = orders[0] if isinstance(orders[0], dict) else orders
                print(f"LATEST ORDER: {json.dumps(latest, ensure_ascii=False)[:400]}")
            else:
                print("NO ORDERS FOUND — webhook did not create an order!")
                return 1
        else:
            print(" ", r.text[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
