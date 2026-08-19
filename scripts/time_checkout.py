"""Time the checkout components locally (live Stripe + Neon) to find the 10s+ culprit."""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.production"))
os.environ["APP_ENV"] = "production"
os.environ["COOKIE_SECURE"] = "false"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

# 1. Stripe call
t0 = time.perf_counter()
import stripe

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
t1 = time.perf_counter()
print(f"stripe import: {t1 - t0:.2f}s")

t0 = time.perf_counter()
try:
    sess = stripe.checkout.Session.create(
        mode="payment",
        customer_email="buyer@test.local",
        line_items=[{"price_data": {"currency": "thb", "product_data": {"name": "t"}, "unit_amount": 14900}, "quantity": 1}],
        success_url="https://graxia-os-funnel.vercel.app/checkout/success",
        cancel_url="https://graxia-os-funnel.vercel.app/",
        metadata={"organization_id": "x", "product_id": "y", "funnel_checkout_session_id": "z"},
    )
    print(f"stripe session create: {time.perf_counter() - t0:.2f}s id={sess.id[:15]}...")
except Exception as exc:
    print(f"stripe error: {type(exc).__name__} {str(exc)[:200]}")

# 2. celery task import + apply_async
t0 = time.perf_counter()
from app.tasks.funnel_automation_tasks import check_and_send_abandoned_cart

t1 = time.perf_counter()
print(f"celery task import: {t1 - t0:.2f}s")

t0 = time.perf_counter()
try:
    check_and_send_abandoned_cart.apply_async(args=["x", "y"], countdown=3600)
    print(f"apply_async: {time.perf_counter() - t0:.2f}s OK")
except Exception as exc:
    print(f"apply_async: {time.perf_counter() - t0:.2f}s ERR {type(exc).__name__} {str(exc)[:150]}")
