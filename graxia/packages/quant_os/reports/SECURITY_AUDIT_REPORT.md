# Security Audit Report — Quant OS

**Date:** 2026-07-13
**Auditor:** Security audit agent
**Scope:** Secret exposure, .env handling, deserialization (safe_pickle), webhook auth, SQL injection, CORS, Telegram.

## Executive Summary

No real secrets are hardcoded in production code. All production secrets flow through `core/config.py:_validate_from_env()` via `os.getenv()`. The codebase has a working `scripts/secret_scan.py` (CRITICAL/HIGH/MEDIUM tiers) and a `.gitignore` that correctly excludes `.env`. Webhook endpoints use constant-time HMAC compare and fail-closed. The `safe_pickle.py` allowlist is appropriately restrictive with HMAC sidecar support.

**Net risk: LOW-MEDIUM.** Top fixes: (1) replace `standby-vps-ip` placeholder in `config/.env.example`, (2) tighten `ingest_mt5_logs.py` SQL f-string, (3) expand logging redaction Bearer pattern to match JWT.

## Severity-Ranked Findings

| # | Sev | File:line | Issue | Recommendation |
|---|---|---|---|---|
| 1 | HIGH | `config/.env.example:4` | Real-looking internal URL `http://standby-vps-ip:8000/activate` exposes VPS topology | Replace with `<standby-host>:<port>/activate` |
| 2 | MED | `scripts/ingest_mt5_logs.py:333` | f-string `CREATE TABLE IF NOT EXISTS {table_name}` — caller-supplied | Validate `table_name` against `^[A-Za-z_][A-Za-z0-9_]*$` |
| 3 | MED | `core/logging_redactor.py:10` | `Bearer\s+[A-Za-z0-9._-]+` misses JWT structure | Verify with sample JWT and add tests |
| 4 | LOW | `api/main.py:142` | CORS `allow_credentials=True` with hardcoded 3-origin list | Move origins to env config |
| 5 | LOW | `api/telegram_commands.py:129` | No rate limit on unauthorized chat_id attempts (only logged) | Add per-IP rate limit |
| 6 | LOW | `scripts/secret_scan.py:59` | Skips `test_*` files unconditionally | Add a CRITICAL bypass for committed tokens |
| 7 | LOW | `core/safe_pickle.py:158` | `copyreg._reconstructor` allowed by `MLUnpickler` without comment | Add comment explaining `__reduce__` safety |

## Hardcoded Secrets

No real (high-entropy, non-placeholder) secrets found in any tracked file.

## safe_pickle.py Review

✅ **Pass.** Correctly restricts unpickler to builtins + numpy + sklearn/xgboost/lightgbm/catboost. Supports HMAC-SHA256 sidecar verification. Caps file size at 100 MB.

## Webhook Signature Verification

| Endpoint | Method | Verdict |
|---|---|---|
| `POST /webhook/tradingview` (HMAC) | HMAC-SHA256, X-Signature, fail-closed | ✅ Strong |
| `POST /webhook/tradingview` (secret) | Constant-time compare, X-Webhook-Secret | ✅ Strong |
| `POST /webhook/generic` | X-API-Key constant-time, fail-closed | ✅ Strong |
| `POST /telegram/webhook` | X-Telegram-Bot-Api-Secret-Token, fail-closed | ✅ Strong |

## SQL Injection Surface

| Location | Pattern | Verdict |
|---|---|---|
| `scripts/setup_warehouse.py` | f-string on static schema | LOW |
| `scripts/ingest_mt5_logs.py:333` | f-string on `table_name` | **MEDIUM — add regex check** |
| `scripts/backup_restore_smoke.py` | f-string with regex validation | ✅ SAFE |
| `scripts/cross_validate.py` | `?` placeholder | ✅ SAFE |
