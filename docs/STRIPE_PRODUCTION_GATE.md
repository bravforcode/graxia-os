# Stripe Production Gate

> Dry-run verification for Stripe integration before enabling live mode.

## Guard Implementation

### Current Status

| Setting | Value | Description |
|---------|-------|-------------|
| `ALLOW_LIVE_STRIPE` | `false` | Blocks live Stripe API calls |
| `STRIPE_SECRET_KEY` | `sk_test_*` only | Must NOT start with `sk_live_` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_*` | Webhook signing secret |

### Enforcement

1. `ALLOW_LIVE_STRIPE=false` disables all Stripe write operations
2. `_stripe_live_mode_blocked()` in `health.py` checks:
   - Key is not empty/placeholder
   - Key does NOT start with `sk_live_`
3. Readiness endpoint verifies: `production_live_providers_disabled` when live mode blocked
4. Production readiness gate requires `live_stripe_blocked` for lock

### Protected Operations (blocked when ALLOW_LIVE_STRIPE=false)

- Creating checkout sessions
- Creating subscriptions
- Creating payment intents
- Refunding charges
- Updating prices/products
- Any Stripe API call that charges real money

### Protected Data (never exposed)

- Stripe secret key — never logged
- Stripe webhook secret — never logged
- Customer payment method details — never logged

## Production Go-Live Checklist

Before setting `ALLOW_LIVE_STRIPE=true`:

- [ ] Stripe account fully verified (business details, banking)
- [ ] Production API keys generated from Stripe Dashboard
- [ ] Webhook endpoint registered with production URL
- [ ] Webhook signing secret matches endpoint
- [ ] Billing plans/price IDs created in production mode
- [ ] Test transaction completed and verified
- [ ] Refund flow tested
- [ ] Webhook delivery verified with Stripe test events
- [ ] Error handling verified for declined cards, insufficient funds
- [ ] Rate limiting verified (prevent duplicate charges)
- [ ] Approval flow verified (human approval required for charges)

## Dry-Run Test Commands

```bash
# Verify live mode is blocked
python -c "from app.config import settings; print(not settings.ALLOW_LIVE_STRIPE)"
# Expected: True

# Verify Stripe key is not live
python -c "from app.config import settings; print(not (settings.STRIPE_SECRET_KEY or '').startswith('sk_live_'))"
# Expected: True

# Verify production readiness endpoint
curl -s http://localhost:8000/api/v1/health/readiness/production | python -m json.tool
# Check: production_ready=false, checks.live_stripe_blocked=true
```
