# Autonomous Trading Loop Security Audit

## Date
2026-07-06

## Summary
- Critical: 2
- High: 4
- Medium: 3
- Low: 2

## Findings

### [CRITICAL] Hardcoded API Keys in Previous Versions Still in Git History
- **File**: `reports/data_pipeline_deep_dive.md:208-210`
- **Description**: The file `reports/data_pipeline_deep_dive.md` contains hardcoded API keys as default values for `ALPHAVANTAGE_API_KEY`, `FRED_API_KEY`, and `NEWS_API_KEY` at lines 208-210. These values (`69A2D75S09YBKLGR`, `ca6997817f1fad59485310fc56ae594e`, `98acea70c06f4dd5ac1489054d877768`) are committed in git history and cannot be removed by simply editing the file.
- **Impact**: Anyone with repo access (including forks and clones) can extract these keys. They may still be valid and provide unauthorized access to AlphaVantage, FRED, and NewsAPI services.
- **Recommendation**: Rotate all three API keys immediately. Scrub git history with `git filter-repo` or BFG Repo Cleaner. Replace with placeholder comments like `REDACTED — set via .env`.

### [CRITICAL] FRED API Key Exposed in URL Query Parameters
- **File**: `core/data/fred_client.py:92,135`
- **Description**: The FRED client logs the API key as a query parameter in request URLs. At lines 92 and 135, the `params` dict includes `"api_key": self._api_key`. If logs are shipped to any centralized logging system, Sentry, or written to world-readable files, the key is exposed in plaintext.
- **Impact**: FRED API key theft via log aggregation systems. The key grants access to economic data feeds used in trading decisions.
- **Recommendation**: Never log query parameters containing secrets. Use a redacted logger adapter or filter `api_key` from structured log output.

### [HIGH] No Telegram Callback User Validation in Autonomous Loop
- **File**: `autonomous/live_approval.py:136-147`
- **Description**: The `handle_callback` method checks `_authorized_users` against `user_id`, but the authorized users set is loaded from `TELEGRAM_ALLOWED_USERS` env var. If this env var is empty (default), `_authorized_users` is an empty set and `if self._authorized_users and user_id not in self._authorized_users` evaluates to `False`, bypassing the check entirely. Any Telegram user who discovers the bot token can approve trades.
- **Impact**: Unauthorized trade approval in live mode. An attacker with the bot token (leaked via logs or other means) could approve arbitrary trades.
- **Recommendation**: Fail-closed — if `TELEGRAM_ALLOWED_USERS` is empty, reject all callbacks instead of allowing all. Add `if not self._authorized_users: return` before the auth check.

### [HIGH] Rate Limiter Does Not Cover Telegram API Calls
- **File**: `autonomous/rate_limiter.py:22-26`
- **Description**: `RateLimiter` only tracks LLM provider buckets (groq, cerebras, openrouter). Telegram API calls in `live_approval.py` and `notifications.py` have no global rate limiting. A rapid cascade of trade decisions could flood the Telegram bot with messages, hitting Telegram's 30 msgs/sec bot limit and causing message drops.
- **Impact**: Lost approval requests, missed trade notifications, potential Telegram bot token ban for rate limit violations.
- **Recommendation**: Add a Telegram-specific rate limiter bucket or use the existing `_rate_limit` in `live_approval.py` as a global limiter shared with `notifications.py`.

### [HIGH] No TLS Verification on Telegram API Calls
- **File**: `autonomous/live_approval.py:210,235`
- **Description**: `httpx.AsyncClient(timeout=10)` is created without explicit `verify=True`. While httpx defaults to verifying TLS, there is no `SSLContext` pinning. On systems with misconfigured CA bundles or MITM proxies, the bot token in the POST body could be intercepted.
- **Impact**: Man-in-the-middle interception of Telegram bot token during approval requests.
- **Recommendation**: Explicitly set `verify=True` and consider pinning `TELEGRAM_API_FINGERPRINT` in production.

### [HIGH] Error Messages Leak Internal State
- **File**: `autonomous/order_executor.py:388-397`
- **Description**: When broker submission fails, the raw exception message is stored in `ExecutionResult.error` and logged at `error` level via `logger.error("order_executor.submit_failed", ..., error=str(exc))`. Broker exceptions may contain connection strings, internal IPs, or partial credentials.
- **Impact**: Internal infrastructure details exposed in logs. If logs ship to a monitoring service, this leaks network topology.
- **Recommendation**: Sanitize broker exceptions before logging. Log the exception type and a hashed error code, not the full message. Store full details only in an encrypted audit trail.

### [MEDIUM] SQLite Database Stored Without Encryption at Rest
- **File**: `autonomous/persistence.py:78-81`
- **Description**: The SQLite database at `data/autonomous_trades.db` stores trade decisions, execution logs, and health data in plaintext. The database file has no encryption and the directory permissions are not explicitly set.
- **Impact**: Local privilege escalation or backup exposure reveals full trading history, strategy reasoning, and account metadata.
- **Recommendation**: Use SQLCipher for encrypted SQLite, or ensure the `data/` directory has `chmod 600` permissions. For production, migrate to PostgreSQL with TLS.

### [MEDIUM] LLM Response Parsing Allows Partial JSON Injection
- **File**: `autonomous/decision_engine.py:375-394`
- **Description**: `_extract_json` uses `re.search(r"\{.*\}", text, re.DOTALL)` as a fallback to extract JSON from LLM responses. The `.*` with `DOTALL` is greedy and could match across multiple JSON objects if the LLM returns concatenated responses, potentially extracting a malformed object.
- **Impact**: Low-probability but possible extraction of incorrect JSON fields from malformed LLM output, leading to erroneous trade signals.
- **Recommendation**: Use a non-greedy match `r"\{.*?\}"` or validate the extracted JSON against a schema (e.g., `jsonschema`) before processing.

### [MEDIUM] Daily Loss Check Uses Absolute Value, Not Realized P&L
- **File**: `autonomous/order_executor.py:477-482`
- **Description**: `_check_daily_loss_breached` compares `abs(self._daily_realized_pnl)` against `MAX_DAILY_LOSS_PCT`, but `MAX_DAILY_LOSS_PCT` is a percentage (e.g., 3.0) while `_daily_realized_pnl` is an absolute dollar amount. The comparison mixes units — a $3 loss would not trip a 3% limit on a $10,000 account.
- **Impact**: Daily loss gate may not trigger when it should, allowing excessive losses.
- **Recommendation**: Normalize the check: `abs(float(self._daily_realized_pnl)) / account_equity * 100 >= MAX_DAILY_LOSS_PCT`, or express the limit in absolute terms and pass account equity into the check.

### [LOW] .env File Present on Disk in Production
- **File**: `.env`
- **Description**: The `.env` file containing all secrets (MT5 credentials, Telegram token, LLM API keys, JWT secrets) exists on disk in plaintext. While gitignored, any process running on the host can read it.
- **Impact**: Local process compromise exposes all credentials.
- **Recommendation**: Use a secrets manager (Vault, AWS Secrets Manager) or at minimum set file permissions to `600` for the trading user only.

### [LOW] Health Check in Dockerfile Is a No-Op
- **File**: `docker/Dockerfile` (proposed)
- **Description**: The HEALTHCHECK `python -c "import sys; sys.exit(0)"` always succeeds regardless of actual system health. It does not verify that the trading loop is running, the broker is connected, or the LLM providers are reachable.
- **Impact**: Docker/Kubernetes will report the container as healthy even when the autonomous loop has crashed or is in an error state.
- **Recommendation**: Implement a proper health endpoint (e.g., check process alive + last decision timestamp < threshold) and use it in the HEALTHCHECK.

## Recommendations

1. **Rotate all exposed API keys immediately** — FRED, AlphaVantage, NewsAPI keys found in `reports/data_pipeline_deep_dive.md`. Scrub git history.
2. **Fix Telegram auth fail-closed** — Reject all callbacks when `TELEGRAM_ALLOWED_USERS` is empty.
3. **Sanitize broker exceptions** — Never log raw `str(exc)` from broker connections; redact connection strings and internal IPs.
4. **Add Telegram rate limiting** — Share a global rate limiter across `live_approval.py` and `notifications.py`.
5. **Normalize daily loss check** — Ensure `MAX_DAILY_LOSS_PCT` is compared against percentage of account equity, not absolute P&L.
6. **Encrypt SQLite at rest** — Use SQLCipher or restrict `data/` directory permissions.
7. **Implement proper Docker HEALTHCHECK** — Verify the trading loop process is alive and responsive.
8. **Pin TLS for Telegram API** — Explicitly set `verify=True` on all httpx clients.
