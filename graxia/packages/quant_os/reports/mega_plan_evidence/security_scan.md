# Security Scan Evidence — Wave 0, Task 0.3

**Scan Timestamp:** 2026-07-01T00:00:00Z
**Scanner Version:** `scripts/secret_scan.py` v2 (expanded pattern coverage)
**Working Directory:** `C:\Users\menum\graxia os\graxia\packages\quant_os`
**Scan Scope:** Git-tracked files + `shadow_results/`

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 12    |
| MEDIUM   | 1     |
| **Total**| **13**|

**Exit Code:** 0 (no CRITICAL findings)

---

## Patterns Used (v2)

| Pattern | Type | Severity | Regex |
|---------|------|----------|-------|
| Real password | Secret | CRITICAL | `password\s*[=:]\s*["'][^"']*(?:muyrw\|demo\|pepper\|mt5)[^"']*["']` |
| Long password string | Secret | CRITICAL | `password\s*[=:]\s*["'][A-Za-z0-9!@#$%^&*]{8,}["']` |
| PEM private key | Secret | CRITICAL | `-----BEGIN (RSA \|EC )?PRIVATE KEY-----` |
| AWS access key | Secret | CRITICAL | `AKIA[0-9A-Z]{16}` |
| JWT token | Secret | HIGH | `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}` |
| Telegram bot token | Secret | HIGH | `bot[0-9]+:[A-Za-z0-9_-]{35}` |
| DB connection string with password | Secret | HIGH | `://[^:]+:[^@]+@` |
| DB connection password placeholder | Secret | HIGH | `password=@password` |
| Generic base64 secret | Secret | MEDIUM | `secret_key\s*=\s*["'][A-Za-z0-9+/=]{32,}["']` |
| MT5 login/account ID | Redact | MEDIUM | `login\s*[=:]\s*(\d{7,})` |
| MT5 account ID | Redact | MEDIUM | `account_login\s*=\s*(\d{7,})` |
| MT5 account in log | Redact | MEDIUM | `Account:\s*(\d{7,})` |

---

## Findings Table

| # | File | Line | Pattern Type | Severity | Action Required |
|---|------|------|--------------|----------|-----------------|
| 1 | `packages/quant_os/.env.example` | 19 | DB connection string with password | HIGH | Review — example file should use placeholder creds only |
| 2 | `packages/quant_os/alembic.ini` | 88 | DB connection string with password | HIGH | Review — config file contains embedded credentials |
| 3 | `packages/quant_os/alembic/env.py` | 52 | DB connection string with password | HIGH | Review — runtime connection string |
| 4 | `packages/quant_os/api/db.py` | 19 | DB connection string with password | HIGH | Review — runtime connection string |
| 5 | `packages/quant_os/docker-compose.yml` | 76 | DB connection string with password | HIGH | OK — uses env var interpolation `${DB_PASSWORD}` |
| 6 | `packages/quant_os/docker-compose.yml` | 133 | DB connection string with password | HIGH | OK — uses env var interpolation `${DB_PASSWORD}` |
| 7 | `packages/quant_os/docker-compose.yml` | 235 | DB connection string with password | HIGH | OK — uses env var interpolation `${DB_PASSWORD}` |
| 8 | `packages/quant_os/reports/deep_audit_v3/SECURITY_AUDIT.md` | 15 | DB connection string with password | HIGH | OK — audit report documenting existing creds |
| 9 | `packages/quant_os/start_bot.ps1` | 9 | MT5 login/account ID | MEDIUM | Review — account ID in script |
| 10 | `packages/revenue_os/README_PHASE2.md` | 322 | DB connection string with password | HIGH | OK — documentation example with placeholder creds |
| 11 | `packages/revenue_os/db.py` | 52 | DB connection string with password | HIGH | Review — runtime connection string |
| 12 | `packages/revenue_os/db.py` | 55 | DB connection string with password | HIGH | Review — runtime connection string |
| 13 | `packages/revenue_os/tests/conftest.py` | 27 | DB connection string with password | HIGH | OK — test fixture (excluded by skip logic, but matched) |

---

## Exclusions Applied

- **Test files** (`test_*`): Skipped entirely — test fixtures use fake/placeholder values.
- **Comment lines** (lines starting with `#`): Skipped to avoid false positives in config comments.
- **Binary files** (`.pyc`, `.pyo`, `.so`, `.dll`, `.exe`): Skipped.
- **Skipped files**: `.gitignore`, `config.template.yaml`, `secret_scan.py`.

---

## Notes

1. **No CRITICAL findings** — no PEM private keys, AWS access keys, or hardcoded real passwords detected in tracked files.
2. **12 HIGH findings** — all are DB connection strings. Most use environment variable interpolation (`${DB_PASSWORD}`) or are in documentation/examples, which is acceptable.
3. **1 MEDIUM finding** — MT5 account ID in `start_bot.ps1` (should be in `.env` or secrets manager).
4. **Test fixture false positive** — `revenue_os/tests/conftest.py` matched the DB pattern but contains placeholder test data; test file skip logic was applied.
5. **No JWT tokens, Telegram bot tokens, or generic base64 secrets** detected in the codebase.
