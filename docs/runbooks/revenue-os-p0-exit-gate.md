# Revenue OS P0 — Exit Gate Checklist

All items must pass before P1 (Launch + warm leads) starts.

## Automated (CI)
- [ ] `pytest graxia/packages/revenue_os/tests/ -q` — no new failures
- [ ] `test_e2e_subscription_flow.py` — full flow green

## Manual (Stripe test mode — founder)
- [ ] Checkout session created for Starter (฿499) via API
- [ ] Complete payment with test card `4242 4242 4242 4242`
- [ ] Webhook `checkout.session.completed` received → order PAID
- [ ] Webhook `customer.subscription.created` received → Subscription row active
- [ ] Billing portal session returns a working URL
- [ ] Kill switch trigger → new checkout returns 503; reset → works again
- [ ] Stripe dashboard test events all return 200

## Deploy
- [ ] `https://graxia-revenue-os.onrender.com/api/system/readiness` → 200
- [ ] Stripe webhook endpoint registered with production URL