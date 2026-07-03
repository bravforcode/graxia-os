# PHASE 20 — SECURITY AUDIT
*Per R1–R18. Credentials cannot leak; system cannot be compromised.*

---

## 20.1 — MT5 Credentials

- Storage: `.env` on disk (loaded by `python-dotenv`, `requirements.txt:13`).
- **`.env` CONTENTS (READ DIRECTLY):** contains live secrets in plaintext —
  - `MT5_LOGIN=61547941`, `MT5_PASSWORD=Graxia-12345`, `MT5_SERVER=Pepperstone-Demo` (`.env:2-4`)
  - `TELEGRAM_BOT_TOKEN=8757840873:AAEA3lHrGoRvPsjJRgxdT5so0sbafHn-t74` (`.env:12`)
  - `GROQ_API_KEY=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` (`.env:27`)
  - `GOOGLE_AI_KEY=…`, `CEREBRAS_API_KEY=…`, `OPENROUTER_API_KEY=…`, `COHERE_API_KEY=…` (`.env:29-39`)
  - `JWT_SECRET_KEY=…`, `WEBHOOK_HMAC_SECRET=…`, `ADMIN_API_KEY=graxia-admin-…` (`.env:49-51`)
  - `DATABASE_URL=postgresql+asyncpg://postgres:postgres@…` (`.env:46`) — **default postgres/postgres creds**
- **Credentials logged?** `runtime/redaction.py:8` redacts `(password|passwd|pwd)\s*[=:]\s*\S+` in logs; `runtime/secret_scan.py` and `scripts/secret_scan.py` scan for plaintext. Redaction *infrastructure* present. **Whether every logger respects it `[UNVERIFIED repo-wide]`** — `mt5_connector/connection.py` does not log the password. Telegram notifier (`monitoring/telegram.py:26-28`) stores token in `self.bot_token` and builds URL — not logged in the read portion. → P2 (redaction coverage).
- **`.gitignore` excludes `.env`?** YES — `.gitignore:15` has `.env`. ✓

## 20.2 — Git History Secrets Scan — THE CRITICAL CHECK

Ran (this session):
- `git ls-files --error-unmatch .env` → **NOT tracked** (error: "did not match any file"). ✓ `.env` is gitignored and was never committed.
- `git ls-files --error-unmatch Meta/pepperstone_creds.txt` → **NOT tracked**. ✓
- `git log --all --oneline --name-only -- .env` → **empty** (never committed). ✓
- `git grep -l -i "Graxia-12345\|61547941\|gsk_J2RRyBj" $(git rev-list --all)` → **empty** (the actual secret *values* never appear in any tracked file in any commit). ✓
- `mt5_connector/config.yaml` → **IS tracked** (`git ls-files` matched) but contains only `path: ""`, `symbols: [XAUUSD]`, no secrets. ✓

**Verdict: secrets are NOT in git history.** The `.env` discipline held. This is a genuine positive — many projects fail this check; this one passes it.

**However:** `Meta/pepperstone_creds.txt` exists on disk with `LOGIN=`/`PASSWORD=` empty (template) — fine. But the *real* secrets live in `.env` on the local Windows machine. **If this machine, a backup, a synced cloud drive, or a VPS image is exfiltrated or lost, all secrets are compromised** (MT5 password, 5 LLM API keys, Telegram bot, JWT/admin keys). The git-history cleanliness does not protect against host compromise. → **P1: rotate all secrets if the host was ever exposed; treat `.env` as a crown-jewel file.**

## 20.3 — API Keys

All third-party keys (Groq, Google AI, Cerebras, OpenRouter, Cohere, Telegram) live in `.env` — not in source. ✓ (per 20.1/20.2). `core/config.py:146-153` reads them via `os.getenv`. No hardcoded keys in `.py`/`.yaml`/`.json`/`.toml` (grep confirmed — only `os.getenv` patterns and test placeholders).

## 20.4 — Secrets Management Table

| Item | Status | Severity | Evidence |
|---|---|---|---|
| MT5 credentials in source code | NO | Critical | `grep` clean; `.env` only |
| MT5 credentials in git history | NO | Critical | `git grep $(git rev-list --all)` empty |
| API keys in source code | NO | Critical | `.env` only |
| `.env` excluded from git | YES | High | `.gitignore:15` |
| Credentials printed to logs | UNVERIFIED (partial) | High | redaction infra present; full coverage unverified |
| Credentials in test files | NO (placeholders only) | High | `tests/test_phase_be_p0.py:75` uses `secret123` placeholder |
| No secrets-management tool used | YES (plain `.env`) | Medium | no Vault/AWS SM; `.env` on local disk |

## 20.5 — Infrastructure / Host Security

- VPS deployment documented (`Meta/aws_deployment_guide.md`, `Meta/gcloud_deployment_guide.md`, `scripts/deploy_vps.ps1`, `infra/systemd/`).
- RDP/SSH IP allowlist, key-based auth, OS patch level: `[UNVERIFIED — requires inspecting the actual VPS, not the repo]`. → P1 once deployed.
- MT5 auto-login: `mt5_connector/connection.py:61` `mt5.initialize(path=path, timeout=timeout)` uses the terminal's stored credentials — recoverable by anyone with filesystem access to the MT5 terminal data folder. → P2.

---

## Phase 20 — Verdict

**STATUS: PARTIAL (strong on the hardest check, weak on host).**

**Strength (stated plainly):** Secrets are **NOT in git history** — verified by `git grep` across all commits. `.env` is gitignored. This is the single most-failed security check in solo projects, and this repo passes it.

**Weaknesses:**
1. **`.env` on local disk contains ALL live secrets in plaintext** (MT5 password, 5 API keys, Telegram token, JWT/admin keys). Host compromise = total compromise. → P1
2. **`DATABASE_URL` uses default `postgres:postgres`** (`.env:46`). → P1
3. No secrets manager (Vault etc.). Plain `.env`. → P2.
4. Host/VPS hardening unverified. → P1 once live.
