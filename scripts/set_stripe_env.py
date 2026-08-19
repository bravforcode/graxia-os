"""
Set/update Stripe env vars on Vercel and verify the webhook endpoint.

Usage:
    # 1. Put values in .env.production (STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY,
    #    STRIPE_WEBHOOK_SECRET) — or export them in the shell.
    # 2. python scripts/set_stripe_env.py

The script:
    - reads the three Stripe vars from the environment
    - verifies the secret key works (balance call) and shows the mode (test/live)
    - lists the registered webhook endpoints and checks ours is present
    - pushes all three vars to the Vercel production environment
"""
import os
import subprocess
import sys

import stripe
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.production"))

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def main() -> int:
    sk = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    pk = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
    whsec = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()

    if not sk:
        print("MISSING: STRIPE_SECRET_KEY (sk_...). Set it in .env.production or export it.")
        return 1
    if not pk:
        print("WARN: STRIPE_PUBLISHABLE_KEY is empty (only needed for client-side Stripe.js).")
    if not whsec:
        print("WARN: STRIPE_WEBHOOK_SECRET is empty — webhook events will FAIL signature "
              "verification until it is set. Get it from Stripe Dashboard -> Webhooks -> "
              "your endpoint -> 'Signing secret'.")

    # 1. Verify the secret key works + show mode
    stripe.api_key = sk
    try:
        bal = stripe.Balance.retrieve()
        mode = "LIVE" if sk.startswith("sk_live") else "TEST"
        avail = sum(x.amount for x in bal.available) / 100
        print(f"OK: Stripe key valid — mode={mode}, available balance={avail:.2f} {bal.available[0].currency.upper() if bal.available else '?'}")
    except stripe.error.AuthenticationError as exc:
        print(f"FAIL: Stripe key rejected — {exc}")
        return 1

    # 2. Check webhook endpoints
    try:
        whs = stripe.WebhookEndpoint.list(limit=20)
        ours = "https://graxia-os-funnel.vercel.app/api/v1/funnel/webhooks/stripe"
        found = [w for w in whs.data if w.url == ours]
        if found:
            print(f"OK: webhook endpoint exists (status={found[0].status}) events={found[0].enabled_events}")
        else:
            print("WARN: webhook endpoint NOT found. Create it: Stripe -> Webhooks -> Add endpoint -> "
                  f"{ours} -> events: checkout.session.completed, checkout.session.expired")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not list webhooks: {exc}")

    # 3. Push to Vercel production env
    for name, value in (("STRIPE_SECRET_KEY", sk), ("STRIPE_PUBLISHABLE_KEY", pk), ("STRIPE_WEBHOOK_SECRET", whsec)):
        subprocess.run(f"vercel env rm {name} production --yes", capture_output=True, text=True, shell=True, cwd=REPO)
        r = subprocess.run(
            f"vercel env add {name} production --yes",
            input=value,
            capture_output=True,
            text=True,
            shell=True,
            cwd=REPO,
        )
        ok = "Added" in r.stdout or "added" in r.stdout.lower() or r.returncode == 0
        print(f"{'SET' if ok else 'FAIL'}: {name} ({'set' if value else 'EMPTY'})")

    print("DONE. Redeploy for env changes to take effect: vercel deploy --prod --yes --archive=tgz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
