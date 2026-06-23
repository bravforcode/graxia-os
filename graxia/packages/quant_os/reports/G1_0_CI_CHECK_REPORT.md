# G1.0 CI Check Report

**Date:** 2026-06-23

## CI Script Created

- `scripts/ci_security_check.py`

Script performs two independent scans:
1. **Secret scan** — detects credential patterns (password, API key, secret, token, MT5 env vars) across `.py`, `.yaml`, `.yml`, `.json`, `.toml`, `.ini`, `.env`, `.md`, `.txt` files.
2. **Forbidden execution-import scan** — detects `order_send` and `TRADE_ACTION_*` imports outside the allowlist (`execution/demo_canary/order_submission.py`).

## CI Scan Run Results

**Status: FAIL**

| Scan | Findings | Detail |
|------|----------|--------|
| Secret scan | 16 | MT5 env vars in archived docs, test credential patterns in reports |
| Forbidden import scan | 116 | `order_send`/`TRADE_ACTION_*` used across `broker/`, `execution/`, `shadow/`, `tests/`, `live_readiness/`, `gold_bot/`, `repo_intelligence/` |
| **Total** | **132** | |

## Test Results

**3/3 passed**

| Test | Result |
|------|--------|
| `test_ci_scan_clean_file` — clean temp file, expect 0 findings | PASS |
| `test_ci_scan_detects_password` — file with `password = "real_secret"`, expect 1 finding | PASS |
| `test_ci_scan_forbidden_import` — file with `order_send` outside allowlist, expect finding | PASS |

## Key Note

CI checks run **independently of local git hooks**. The script at `scripts/ci_security_check.py` requires no hook installation, reads files directly from disk, and can be invoked from any CI pipeline, manual run, or pre-push hook without depending on the local hook infrastructure at `repo_intelligence/hooks/`.

## Files Changed

- `scripts/ci_security_check.py` — new CI security check script
- `tests/test_ci_security_check.py` — new unit tests for the CI script
- `reports/G1_0_CI_CHECK_REPORT.md` — this report
