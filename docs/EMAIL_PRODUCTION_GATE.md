# Email Production Gate

> Dry-run verification for email delivery (Resend) before enabling live mode.

## Guard Implementation

### Current Status

| Setting | Value | Description |
|---------|-------|-------------|
| `ALLOW_REAL_EMAIL_SEND` | `false` | Blocks real email sending |
| `RESEND_API_KEY` | Placeholder/test | Must be real Resend API key |

### Enforcement

1. `ALLOW_REAL_EMAIL_SEND=false` blocks all email delivery
2. `_real_email_send_blocked()` in `health.py` checks:
   - Key is not empty/placeholder
3. All email operations route through `email_service.py` which checks `ALLOW_REAL_EMAIL_SEND`
4. Production readiness gate requires `real_email_send_blocked` for lock

### Protected Operations (blocked when ALLOW_REAL_EMAIL_SEND=false)

- Sending outreach emails
- Sending notification emails
- Sending verification emails
- Sending password reset emails
- Any Resend API call

### Protected Data (never exposed)

- Resend API key — never logged
- Email content for denied requests — never logged
- Recipient addresses for denied requests — redacted from audit

## Production Go-Live Checklist

Before setting `ALLOW_REAL_EMAIL_SEND=true`:

- [ ] Sending domain verified with Resend (DNS records)
- [ ] SPF, DKIM, DMARC records configured
- [ ] Production Resend API key generated (not test key)
- [ ] Rate limits verified (Resend daily quota)
- [ ] Bounce handling configured
- [ ] Spam score tested
- [ ] Email template reviewed for all variables
- [ ] Approval flow verified (human approval before auto-send)
- [ ] Unsubscribe link present and functional
- [ ] `FROM_EMAIL` uses verified domain
- [ ] Rate limiting verified (prevent accidental mass send)

## Dry-Run Test Commands

```bash
# Verify real email send is blocked
python -c "from app.config import settings; print(not settings.ALLOW_REAL_EMAIL_SEND)"
# Expected: True

# Verify production readiness endpoint
curl -s http://localhost:8000/api/v1/health/readiness/production | python -m json.tool
# Check: production_ready=false, checks.real_email_send_blocked=true
```
