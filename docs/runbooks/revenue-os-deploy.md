# Revenue OS — Deploy Runbook (Render)

## 1. Deploy
1. Push `render.yaml` change to GitHub main.
2. Render Dashboard → Blueprint → Connect repo (or "Update" existing blueprint).
3. Fill manual env vars in Render dashboard:
   - `STRIPE_SECRET_KEY` — live key (from `.env.graxia`, never commit)
   - `STRIPE_WEBHOOK_SECRET` — from Stripe webhook endpoint (Step 3)
   - `ADMIN_API_KEY` — strong random value
4. Deploy. Wait for healthcheck `/api/system/readiness` to go green.

## 2. Verify API
```bash
curl -s https://graxia-revenue-os.onrender.com/api/system/readiness
# Expected: {"status":"ready", ...} (200)
```

## 3. Register Stripe webhook (founder action)
1. Stripe Dashboard → Developers → Webhooks → Add endpoint:
   - URL: `https://graxia-revenue-os.onrender.com/api/checkout/stripe-webhook`
   - Events: `checkout.session.completed`, `charge.refunded`,
     `customer.subscription.created`, `customer.subscription.deleted`
2. Copy the signing secret (`whsec_...`) into Render env `STRIPE_WEBHOOK_SECRET`.
3. Send a test event from the dashboard → confirm 200 + `"status":"success"`.

## 4. Money-path smoke (Stripe test mode)
1. Create a test checkout session (Starter product) via the API.
2. Complete payment with Stripe test card `4242 4242 4242 4242`.
3. Confirm webhook received → order PAID + subscription mirror row created.