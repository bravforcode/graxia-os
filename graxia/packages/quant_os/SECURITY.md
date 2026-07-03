# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in quant_os, please report it via email to **[security@graxia.dev](mailto:security@graxia.dev)** — do **not** open a public GitHub issue.

Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigation (if known)

We aim to acknowledge receipt within 48 hours and provide a fix or mitigation timeline within 5 business days.

## Scope

Security coverage applies to:

- Core trading logic (`core/`, `execution/`, `risk/`, `strategies/`, `validation/`)
- API surface (`api/`, `broker/`)
- Authentication and credential handling
- Dataset and configuration integrity
- Dependency supply chain (via pre-commit and CI scanning)

Out of scope:

- Backtest and research outputs (treated as non-production artifacts)
- Third-party broker APIs (responsibility lies with the broker)
- Development-only scripts and test fixtures

## Best Practices

- Never commit secrets, API keys, or credentials to the repository
- Use environment variables (`.env`) for all sensitive configuration
- Run `detect-private-key` pre-commit hook locally
- Keep dependencies updated via regular `pip audit` or Dependabot

---

## Secret Inventory

> **WARNING:** Actual secret values MUST NEVER appear in this file, source code, logs, or git history.

| # | Secret | Env Var | Used By | Classification |
|---|--------|---------|---------|----------------|
| 1 | MT5 Login / Password / Server | `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` | `execution/adapters/mt5_adapter.py`, broker connection | CRITICAL — controls live trading |
| 2 | Telegram Bot Token | `TELEGRAM_BOT_TOKEN` | `telegram_monitor.py`, notification dispatch | HIGH — impersonation risk |
| 3 | Telegram Chat ID | `TELEGRAM_CHAT_ID` | Same as above | MEDIUM — info disclosure |
| 4 | PostgreSQL DSN | `DATABASE_URL` | `revenue_os.db`, all ORM sessions | CRITICAL — full data access |
| 5 | JWT Signing Key | `JWT_SECRET_KEY` | Token issuance/verification | CRITICAL — session forgery |
| 6 | Admin API Key | `ADMIN_API_KEY` | `api/admin.py` `verify_admin()` | CRITICAL — admin takeover |
| 7 | Webhook HMAC Secret | `WEBHOOK_HMAC_SECRET` | `api/webhook.py` `verify_webhook_signature()` | HIGH — signal injection |
| 8 | Broker API Keys (Pepperstone/IC) | `BROKER_API_KEY`, `BROKER_API_SECRET` | Broker adapters | CRITICAL — fund access |

---

## Rotation Plan

### Rotation Schedule

| Secret | Max Age | Trigger | Owner |
|--------|---------|---------|-------|
| MT5 Password | 90 days | Compromise, personnel change | Trading Ops |
| Telegram Bot Token | 180 days | Compromise, bot re-registration | DevOps |
| PostgreSQL DSN/Password | 90 days | Compromise, infra migration | DevOps |
| JWT Signing Key | 30 days | Compromise, scheduled | Backend Lead |
| Admin API Key | 90 days | Compromise, personnel change | Security Lead |
| Webhook HMAC Secret | 90 days | Compromise, scheduled | Backend Lead |
| Broker API Keys | Per broker policy | Compromise, broker mandate | Trading Ops |

### Rotation Procedure (per secret)

1. **Generate** new secret value via secure random or provider console.
2. **Deploy** new value to secrets manager / env (both old + new valid during grace).
3. **Restart** services to pick up new value.
4. **Verify** functionality with smoke test.
5. **Revoke** old value after grace period (24h for JWT, 48h for others).
6. **Audit** — log rotation event in audit trail with timestamp and operator.

### MT5 Password Rotation
```bash
# 1. Change password in MetaTrader 5 terminal
# 2. Update MT5_PASSWORD in secrets manager
# 3. Restart bot: python scripts/start_bot.py
# 4. Verify: python scripts/mt5_verify.py
```

### JWT Key Rotation
```python
# Grace period: accept tokens signed with OLD or NEW key
# After grace period: only NEW key
# Implementation: SecretProvider.rotate(old_key, new_key, grace_hours=24)
```

### Admin API Key / Webhook HMAC Rotation
```bash
# 1. Generate: python -c "import secrets; print(secrets.token_urlsafe(48))"
# 2. Update env var
# 3. Restart API: python api/main.py
# 4. Update all webhook consumers with new HMAC secret
# 5. Revoke old key
```

---

## Git History Cleanup Plan

If secrets have been committed to git history:

### Detection
```bash
# Scan for secrets in current and historical commits
git log --all --diff-filter=D -- "*.env" "*.env.*"
python scripts/secret_scan.py  # repo-local scanner
trufflehog git file://. --only-verified
```

### Cleanup Steps

1. **Immediate:** Rotate ALL exposed secrets (treat as compromised).
2. **Rewrite history** using `git filter-repo`:
   ```bash
   pip install git-filter-repo
   git filter-repo --path .env --path scripts/.env --invert-paths
   git filter-repo --replace-text <(echo 'OLD_SECRET_VALUE==>REDACTED')
   ```
3. **Force push** to all remotes (coordinate with team).
4. **Add** `.env*` patterns to `.gitignore` if not already present.
5. **Verify** no secrets remain: `trufflehog git file://. --only-verified`.
6. **Document** incident in audit log with date, operator, and affected commits.

### Prevention
- `.gitignore` must include: `.env`, `.env.*`, `*.pem`, `*.key`
- Pre-commit hook: `detect-private-key`, `gitleaks`
- CI step: `trufflehog` scan on every PR

---

## SecretProvider.rotate() API Recommendation

```python
"""
Recommended API for programmatic secret rotation.

Integrates with secrets manager (Vault, AWS SSM, env-based fallback).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class RotatedSecret:
    """Result of a secret rotation."""
    key: str
    old_version: Optional[str]  # version id, NOT the value
    new_version: str
    rotated_at: datetime
    grace_until: Optional[datetime]


class SecretProvider(ABC):
    """Abstract base for secret management."""

    @abstractmethod
    def get(self, key: str) -> str:
        """Retrieve current secret value. Raises if not found."""

    @abstractmethod
    def rotate(self, key: str, new_value: str, grace_hours: int = 48) -> RotatedSecret:
        """
        Atomically rotate a secret.

        - Stores new_value as the active version.
        - Keeps old version readable for grace_hours.
        - After grace period, old version is permanently deleted.
        - Returns RotatedSecret metadata (never the actual values).
        """

    @abstractmethod
    def revoke(self, key: str, version: Optional[str] = None) -> None:
        """Immediately revoke a secret (or specific version)."""


# Env-based implementation (MVP)
class EnvSecretProvider(SecretProvider):
    """Secrets from environment variables. No rotation persistence."""

    def get(self, key: str) -> str:
        import os
        val = os.environ.get(key)
        if not val:
            raise KeyError(f"Secret {key} not found in environment")
        return val

    def rotate(self, key: str, new_value: str, grace_hours: int = 48) -> RotatedSecret:
        import os
        from datetime import datetime, timedelta
        old = os.environ.get(key)
        os.environ[key] = new_value
        return RotatedSecret(
            key=key,
            old_version="env-prev" if old else None,
            new_version="env-current",
            rotated_at=datetime.utcnow(),
            grace_until=datetime.utcnow() + timedelta(hours=grace_hours),
        )

    def revoke(self, key: str, version: Optional[str] = None) -> None:
        import os
        os.environ.pop(key, None)


# Production: use HashiCorp Vault or AWS Secrets Manager
# class VaultSecretProvider(SecretProvider): ...
# class AWSSecretsProvider(SecretProvider): ...
```

### Integration Points
- `core/config.py` → `SecretProvider` injected at startup
- `api/admin.py` → admin endpoint to trigger rotation
- Audit log → every `rotate()` / `revoke()` call logged with operator identity
