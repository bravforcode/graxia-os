# Google Workspace Production Gate

> Dry-run verification for Google Workspace integration (Gmail, Calendar, Drive) before enabling write scopes.

## Guard Implementation

### Current Status

| Setting | Value | Description |
|---------|-------|-------------|
| `ALLOW_REAL_GOOGLE_MUTATION` | `false` | Blocks real Google API mutations |
| `GOOGLE_ENABLE_WRITE_SCOPES` | `false` | Disables write OAuth scopes |

### Enforcement

1. `ALLOW_REAL_GOOGLE_MUTATION=false` blocks all write operations
2. `GOOGLE_ENABLE_WRITE_SCOPES=false` prevents OAuth scope requests for write
3. `_real_google_mutation_blocked()` in `health.py` checks both flags
4. Production readiness gate requires `real_google_mutation_blocked` for lock

### Protected Operations (blocked when ALLOW_REAL_GOOGLE_MUTATION=false)

- Sending emails via Gmail API
- Creating/updating Calendar events
- Modifying Google Drive files
- Creating Google Docs/Sheets
- Any Google Workspace mutation that affects real data

### Protected Data (never exposed)

- Google OAuth tokens — never logged
- Google API keys — never logged
- Email content for denied requests — redacted from audit
- Calendar event details — redacted from audit

## Production Go-Live Checklist

Before setting `ALLOW_REAL_GOOGLE_MUTATION=true`:

- [ ] Google Cloud project configured for production
- [ ] OAuth consent screen published (not testing)
- [ ] OAuth scopes verified for minimum access
- [ ] Gmail API enabled in Google Cloud Console
- [ ] Calendar API enabled in Google Cloud Console (if needed)
- [ ] Drive API enabled in Google Cloud Console (if needed)
- [ ] API rate limits reviewed
- [ ] Token refresh mechanism verified
- [ ] Disconnection/re-auth flow tested
- [ ] Approval flow verified (human approval before auto-send)

## Dry-Run Test Commands

```bash
# Verify Google mutation is blocked
python -c "from app.config import settings; print(not settings.ALLOW_REAL_GOOGLE_MUTATION)"
# Expected: True

# Verify write scopes are disabled
python -c "from app.config import settings; print(not settings.GOOGLE_ENABLE_WRITE_SCOPES)"
# Expected: True

# Verify production readiness endpoint
curl -s http://localhost:8000/api/v1/health/readiness/production | python -m json.tool
# Check: production_ready=false, checks.real_google_mutation_blocked=true
```
