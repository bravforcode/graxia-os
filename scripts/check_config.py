"""Gate 0 readiness checker — run after filling real keys in .env.

Usage:
    backend\\venv\\Scripts\\python.exe scripts\\check_config.py

Exits 0 when everything required for SHADOW is present.
Exits 1 when something critical is missing (safe to run repeatedly).
"""
import os
import sys

REQUIRED_FOR_SHADOW = {
    "ADMIN_API_KEY": "admin auth for /api/autonomy + /api/policy (fail-closed in prod)",
    "DATABASE_URL": "app database (Supabase or local)",
}
REQUIRED_FOR_PAYMENTS = {
    "STRIPE_SECRET_KEY": "live sk_live_... before real money; sk_test_... for testing",
    "STRIPE_WEBHOOK_SECRET": "Stripe webhook HMAC secret",
}
REQUIRED_FOR_ALERTS = {
    "TELEGRAM_BOT_TOKEN": "circuit-breaker paging",
    "TELEGRAM_CHAT_ID": "telegram chat to receive alerts",
}
OPTIONAL_FOR_P2 = {
    "SHOPIFY_STORE_DOMAIN": "shopify channel (P2)",
    "SHOPIFY_ACCESS_TOKEN": "shopify admin token (P2)",
    "SHOPIFY_WEBHOOK_SECRET": "shopify webhook HMAC (P2)",
    "SUPPLIER_API_URL": "POD supplier (P2)",
    "SUPPLIER_API_KEY": "POD supplier key (P2)",
    "SUPPLIER_WEBHOOK_SECRET": "supplier webhook HMAC (P2)",
    "META_ACCESS_TOKEN": "Meta ads (P2)",
    "META_AD_ACCOUNT_ID": "Meta ad account (P2)",
}


def load_env(path: str) -> dict:
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def main() -> int:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = load_env(os.path.join(repo, ".env"))
    env.update({k: v for k, v in os.environ.items() if v})  # env overrides

    missing_critical, missing_payment, missing_alert, missing_p2 = [], [], [], []

    for k, why in REQUIRED_FOR_SHADOW.items():
        (missing_critical if not env.get(k) else []).append(f"{k} — {why}")
    for k, why in REQUIRED_FOR_PAYMENTS.items():
        (missing_payment if not env.get(k) else []).append(f"{k} — {why}")
    for k, why in REQUIRED_FOR_ALERTS.items():
        (missing_alert if not env.get(k) else []).append(f"{k} — {why}")
    for k, why in OPTIONAL_FOR_P2.items():
        (missing_p2 if not env.get(k) else []).append(f"{k} — {why}")

    print("=== Gate 0 readiness ===")
    print(f"[{'OK' if not missing_critical else 'MISSING'}] Critical (block SHADOW):")
    for item in missing_critical:
        print(f"      - {item}")
    print(f"[{'OK' if not missing_payment else 'CHECK'}] Payments (block real money):")
    for item in missing_payment:
        print(f"      - {item}")
    print(f"[{'OK' if not missing_alert else 'CHECK'}] Alerts (block paging):")
    for item in missing_alert:
        print(f"      - {item}")
    print(f"[{'OK' if not missing_p2 else 'OPTIONAL'}] Phase 2 channels/ads/supplier:")
    for item in missing_p2:
        print(f"      - {item}")

    stripe = env.get("STRIPE_SECRET_KEY", "")
    if stripe.startswith("sk_test_"):
        print("      ! STRIPE_SECRET_KEY is a TEST key — no real money until sk_live_...")
    elif stripe.startswith("sk_live_"):
        print("      ! STRIPE_SECRET_KEY is LIVE — double-check STRIPE_MODE/ALLOW_LIVE_STRIPE before enabling")

    critical_ok = not missing_critical
    print("\nResult: " + ("READY FOR SHADOW (provision + advance)" if critical_ok
                          else "NOT READY — fill critical keys first"))
    return 0 if critical_ok else 1


if __name__ == "__main__":
    sys.exit(main())
