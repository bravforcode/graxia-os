# PHASE 20 — SECURITY AUDIT
**Date**: 2026-07-05 | **Scope**: Full codebase + git history | **Severity Scale**: P0=Critical P1=High P2=Medium P3=Low

---

## 20.1 MT5 Credentials

### Storage Location
| Credential | Storage | File | Line |
|------------|---------|------|------|
| MT5 Login | .env (gitignored) | `.env.example:7` (template) | `MT5_LOGIN=0` |
| MT5 Password | .env (gitignored) | `.env.example:8` (template) | `MT5_PASSWORD=` |
| MT5 Server | .env (gitignored) | `.env.example:9` (template) | `MT5_SERVER=Pepperstone-Demo` |
| MT5 Login (plaintext) | **Plaintext in working dir** | `Meta/pepperstone_creds.txt.backup:5` | `LOGIN=61547941` |
| MT5 Password (plaintext) | **Plaintext in working dir** | `Meta/pepperstone_creds.txt.backup:6` | `PASSWORD=Graxia-12345` |

### ⚠️ CRITICAL — P0: Plaintext credentials in repository
`Meta/pepperstone_creds.txt.backup` contains:
```
LOGIN=61547941
PASSWORD=Graxia-12345
```
The file header says "DO NOT commit this file to git" but it EXISTS in the working directory. This is a **live security vulnerability**:
- The credentials are readable by any process with filesystem access
- The password is trivially guessable (`Graxia-12345`)
- The account number is exposed
- Even if `.gitignore` covers this file, it's present on disk

### ⚠️ CRITICAL — P0: Config reads password into memory
`core/config.py:162`:
```python
self.mt5_password = os.getenv("MT5_PASSWORD", self.mt5_password)
```
The password is held as a plain string attribute on `QuantConfig`. Any code that logs or serializes the config object could leak it. The `__repr__` of `QuantConfig` is the default dataclass repr which **will print all field values** including `mt5_password`.

### Secret Management Infrastructure
- `runtime/secret_provider.py:16-60` `SecretProvider`: Reads secrets from env vars or files. Has `__repr__` protection.
- `runtime/redaction.py:1-44` `Redactor`: Regex-based redaction patterns.
- `runtime/broker_identity_guard.py:44-89` `BrokerIdentityGuard`: Validates server/login/mode match.

### ⚠️ GAP — P1: SecretProvider not used by config
`SecretProvider` exists but `core/config.py` does its own `os.getenv()` reads. The protected `SecretProvider` is bypassed by the main config flow.

---

## 20.2 Git History Secrets Scan

### CRITICAL FINDING — P0: $ git grep reveals 30 files matching credential patterns

The command `git grep -i "password|api_key|secret|login"` returned **30 file matches** across the entire commit history. Key findings (filenames only, NO actual secrets output):

| File | Contains | Risk |
|------|----------|------|
| `Meta/pepperstone_creds.txt.backup` | Plaintext login + password | **P0 — ACTIVE CREDENTIALS** |
| `config/broker_profile.template.yaml` | Secret/credential field templates | P2 — template risk |
| `core/config.py` | `mt5_password`, `jwt_secret_key`, `webhook_hmac_secret`, `admin_api_key`, `telegram_bot_token` | P1 — all secret fields in memory |
| `core/data/fred_client.py` | FRED API key handling | P2 |
| `api/webhook.py` | Webhook HMAC secret | P2 |
| `api/telegram_server.py` | Telegram token | P2 |
| `data_pipeline/sources/macro_data.py` | API keys for macro data | P2 |
| `data_pipeline/sources/news_sentiment.py` | API keys for news | P2 |
| `api/admin.py` | Admin API key | P2 |
| `api/signal_service.py` | Secrets in signal service | P2 |
| `broker/mt5_gateway.py` | MT5 credentials | P1 |
| `execution/adapters/binance.py` | Binance API keys | P2 |
| `docker-compose.yml` | Database password (`postgres:postgres`) | P3 — dev default |
| `.github/workflows/deploy.yml` | Deployment secrets | P2 |

### ⚠️ CRITICAL — P0: pepperstone_creds.txt.backup is NOT in .env
The `.env` file is gitignored, but `Meta/pepperstone_creds.txt.backup` is a separate credential file that may or may not be gitignored. **Regardless of git status, plaintext credentials in the working tree are a security incident.** The credentials must be:
1. Removed from the filesystem
2. Rotated (the password `Graxia-12345` is compromised)
3. Stored exclusively in a password manager or OS keychain

### ⚠️ Additional: docker-compose.yml has default database password
`docker-compose.yml` contains `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/quant_os` — this is a default credential that may be active in development deployments.

---

## 20.3 API Keys

| Key | Purpose | Storage Location | Status |
|-----|---------|-----------------|--------|
| TELEGRAM_BOT_TOKEN | Telegram alerts | `.env` via `core/config.py:173` | ✅ gitignored |
| TELEGRAM_CHAT_ID | Telegram target | `.env` via `core/config.py:174` | ✅ gitignored |
| FRED_API_KEY | FRED economic data | `.env` via `core/data/fred_client.py` | ⚠️ May be in URLs |
| TV_WEBHOOK_SECRET | TradingView webhook auth | `.env` via `core/config.py:169` | ✅ gitignored |
| ADMIN_API_KEY | API admin access | `.env` via `core/config.py:170` | ✅ gitignored |
| JWT_SECRET_KEY | JWT signing | `.env` via `core/config.py:168` | ✅ gitignored |
| DATABASE_URL | PostgreSQL connection | `.env` via `core/config.py:157` | ⚠️ Contains password in URL |
| REDIS_URL | Redis connection | `.env` via `core/config.py:158` | ✅ gitignored |
| SENTRY_DSN | Error reporting | `.env` via config | ✅ gitignored |
| STANDBY_WEBHOOK_URL | Failover endpoint | `monitoring/health_check.py:80` | ⚠️ env var |
| TELEGRAM_ALLOWED_USERS | Authorization | `risk/kill_switch.py:307` | ⚠️ env var |

### ⚠️ NOTE: FRED API key in URLs
`core/data/fred_client.py` may construct URLs containing the FRED API key as a query parameter. API keys in URLs are logged by proxies, servers, and browsers. This is a **P2** finding if confirmed.

---

## 20.4 Secrets Management Table

| Secret | Storage | Encrypted | Rotated | Access Control | Risk |
|--------|---------|-----------|---------|---------------|------|
| MT5 Login | .env + plaintext file | NO | NO | Filesystem | P0 |
| MT5 Password | .env + plaintext file | NO | NO | Filesystem | P0 |
| Telegram Bot Token | .env | NO | NO | Filesystem | P2 |
| Telegram Chat ID | .env | NO | NO | Filesystem | P3 |
| FRED API Key | .env | NO | NO | Filesystem | P2 |
| Webhook HMAC Secret | .env | NO | NO | Filesystem | P2 |
| Admin API Key | .env | NO | NO | Filesystem | P2 |
| JWT Secret Key | .env | NO | NO | Filesystem | P2 |
| Database Password | .env (embedded in URL) | NO | NO | Filesystem | P2 |
| Redis Password | .env | NO | NO | Filesystem | P3 |
| Sentry DSN | .env | NO | NO | Filesystem | P3 |

**Summary**: ZERO secrets are encrypted at rest. ZERO secrets use a secrets manager (Azure Key Vault, HashiCorp Vault, AWS Secrets Manager). All secrets are plaintext environment variables.

---

## 20.5 Infrastructure / Host Security

### VPS
- **No VPS configuration documented** in the codebase beyond `deploy/` directory and `Meta/gcloud_deployment_guide.md` and `Meta/aws_deployment_guide.md`
- **No IP allowlist** configured for remote access
- **No key-based auth requirement** documented for SSH

### OS Patching
- **Not addressed** in any code or documentation
- No automated patch management

### MT5 Auto-Login Credentials
- MT5 terminal stores auto-login credentials in its own configuration files on the filesystem
- If the VPS is compromised, MT5 credentials may be recoverable from the terminal's stored configuration
- **No assessment of MT5 credential storage security performed**

### ⚠️ GAP — P2: No infrastructure security checklist
The `Meta/broker_verification_report.md` has extensive pre-live checklists but none for infrastructure security (firewall, SSH hardening, fail2ban, disk encryption, process isolation).

---

## Top Findings (Phase 20)

| # | Severity | Finding |
|---|----------|---------|
| 1 | **P0** | Plaintext MT5 credentials in `Meta/pepperstone_creds.txt.backup` — login=61547941, password exposed on filesystem |
| 2 | **P0** | `QuantConfig` dataclass holds `mt5_password` as plain string — default `__repr__` would print it; no redaction on config object |
| 3 | **P0** | 30+ files in git history match credential patterns — full audit needed; at minimum, pepperstone credentials must be rotated |
| 4 | **P1** | `SecretProvider` exists but `core/config.py` bypasses it with direct `os.getenv()` reads — secrets infrastructure unused in main flow |
| 5 | **P1** | ZERO secrets encrypted at rest; no key vault, no hardware security module, all plaintext env vars |
