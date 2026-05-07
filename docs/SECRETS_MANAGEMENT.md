# Secrets Management

Never store production credentials in flat files on disk. This document explains how to
manage secrets properly for Graxia OS.

---

## Recommended: Doppler (simplest)

### One-time setup

```bash
# Install Doppler CLI
curl -Ls https://cli.doppler.com/install.sh | sh

# Authenticate
doppler login

# Create a project
doppler projects create graxia-os
doppler setup --project graxia-os --config prd

# Import existing secrets (one-time, then shred the file)
doppler secrets upload .env.production
shred -u .env.production
```

### Running locally

```bash
doppler run -- docker compose -f docker-compose.dev.yml up
```

### Running in production (server)

```bash
# Install Doppler CLI on the server
doppler run -- docker compose up -d
```

### GitHub Actions

Add `DOPPLER_TOKEN` to GitHub repository secrets, then in your workflow:

```yaml
- uses: dopplerhq/cli-action@v2
- run: doppler run -- python -m pytest tests/
```

---

## Alternative: AWS Secrets Manager

If you prefer AWS:

```python
# In app/config.py, override with:
import boto3, json

def _load_from_aws(secret_name: str) -> dict:
    client = boto3.client("secretsmanager", region_name="ap-southeast-1")
    return json.loads(client.get_secret_value(SecretId=secret_name)["SecretString"])
```

---

## Environment-specific configs

| Environment | Source |
|---|---|
| Local dev | `.env` (gitignored) or `doppler run --` |
| Staging | Doppler `stg` config |
| Production | Doppler `prd` config or AWS Secrets Manager |
| CI/CD | GitHub Secrets + Doppler token |

---

## Generating secrets

```bash
# 64-char SECRET_KEY
openssl rand -hex 32

# ENCRYPTION_KEY (base64)
openssl rand -base64 32

# REDIS_PASSWORD
openssl rand -hex 32

# ADMIN password
openssl rand -base64 24

# INTERNAL_METRICS_TOKEN
openssl rand -hex 32

# AGE backup key
age-keygen -o /tmp/backup-age.txt
# Copy public key to Doppler as BACKUP_ENCRYPTION_PUBLIC_KEY
# Store private key offline (password manager or encrypted USB)
shred -u /tmp/backup-age.txt
```

---

## What must NEVER be committed

- `.env`, `.env.production`, `.env.staging` — real secrets
- `secrets/*.txt` — secret token files
- Any file containing `sk-or-v1-`, `AIzaSy`, `GOCSPX-` patterns

These are already in `.gitignore`. Verify with:

```bash
git ls-files | grep -E "\.env$|secrets/"
# Expected: no output (or only .env.example files)
```
