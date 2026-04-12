# Secret Inventory

This inventory documents production secrets by purpose, minimum requirement, rotation policy, and storage class. It never stores secret values.

| Secret | Env Var | Minimum Requirement | Rotation Period | Owner | Storage Class |
| --- | --- | --- | --- | --- | --- |
| App signing key | `SECRET_KEY` | 64+ chars, high entropy, not a placeholder | 180 days | Platform | Password manager + Docker secret |
| Data encryption key | `ENCRYPTION_KEY` | Fernet-compatible secret or equivalent strong key | 180 days | Platform | Password manager + Docker secret |
| JWT keyset | `JWT_SIGNING_KEYS` | JSON keyset with active `kid`, strong per-key entropy | 90 days | Platform | Password manager + Docker secret |
| Active JWT key id | `JWT_ACTIVE_KID` | Must exist in keyset | On each JWT rotation | Platform | Env config |
| CSRF signing secret | `CSRF_SECRET` | Strong random secret, separate from app default in production | 180 days | Platform | Password manager + Docker secret |
| API compatibility key | `API_KEY` | Strong random secret if enabled | 180 days | Platform | Password manager + Docker secret |
| Postgres password | `POSTGRES_PASSWORD` | 24+ chars, high entropy | 180 days | Platform | Docker secret |
| Redis password | Redis URL/password secret | 24+ chars, high entropy | 180 days | Platform | Docker secret |
| Telegram bot token | `TELEGRAM_BOT_TOKEN` | Real bot token with provider-issued format | 90 days | Ops | Password manager + Docker secret |
| Telegram chat id | `TELEGRAM_CHAT_ID` | Numeric chat identifier | On bot/channel changes | Ops | Env config |
| Alertmanager webhook token | `ALERTMANAGER_WEBHOOK_TOKEN` and `secrets/alertmanager_webhook_token.txt` | 32+ random bytes, bearer-token safe | 90 days | Ops | Password manager + Docker secret file |
| OpenClaw API key | `OPENCLAW_API_KEY` | Provider-issued production key | 90 days | AI Platform | Password manager |
| Gemini API key | `GEMINI_API_KEY` | Provider-issued production key | 90 days | AI Platform | Password manager |
| Google OAuth client id | `GOOGLE_CLIENT_ID` | Provider-issued client id | 180 days | Workspace | Password manager |
| Google OAuth client secret | `GOOGLE_CLIENT_SECRET` | Provider-issued client secret | 180 days | Workspace | Password manager |
| Google refresh token | `GOOGLE_REFRESH_TOKEN` | Provider-issued refresh token | 90 days or on revocation | Workspace | Password manager |
| SerpAPI key | `SERPAPI_KEY` | Provider-issued production key | 90 days | Platform | Password manager |
| Backup encryption private key | `BACKUP_ENCRYPTION_PRIVATE_KEY_FILE` -> `secrets/backup_private_key.txt` | `age` private identity file, never checked into git | 180 days | Platform | Password manager + offline escrow + Docker secret file |
| Backup encryption public key | `BACKUP_ENCRYPTION_PUBLIC_KEY` | Matching `age` public recipient | On key rotation | Platform | Repo-safe env template value only after production key generation |
| Backup object bucket | `BACKUP_BUCKET` | Production S3-compatible bucket with lifecycle policy | On bucket migration | Platform | Env config |
| Backup object region | `BACKUP_REGION` | Provider region identifier | On bucket migration | Platform | Env config |
| Backup object endpoint | `BACKUP_ENDPOINT` | S3-compatible endpoint if not AWS | On bucket migration | Platform | Env config |
| Object store access key | `AWS_ACCESS_KEY_ID` | Provider-issued access key scoped to backup bucket | 90 days | Platform | Password manager |
| Object store secret key | `AWS_SECRET_ACCESS_KEY` | Provider-issued secret key scoped to backup bucket | 90 days | Platform | Password manager |

## Rotation Notes

- Record the last rotation timestamp in the operational runbook, not in this file.
- Production deploys should fail fast when required secrets are missing or still using placeholders.
- JWT rotation must keep the previous key available for at least one refresh-token cycle to avoid breaking in-flight sessions.
