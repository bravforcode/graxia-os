# 🔑 Secret Rotation Guide — URGENT ACTION REQUIRED
**Date:** 2026-04-20  
**Status:** ALL secrets below were exposed in an AI conversation session and MUST be rotated

> [!CAUTION]
> ถ้าคุณอ่านเอกสารนี้ → rotate ทุก key ด้านล่างนี้ทันที ก่อนทำอย่างอื่น

---

## Exposed Secrets (Both Projects)

| Secret | Location | Rotate Where |
|--------|----------|-------------|
| `DB_PASSWORD=7Px70o<?gL` | Thaolai .env.production | Supabase/PostgreSQL → ALTER USER |
| `JWT_SECRET=M0h4UAzcL975l...` | Thaolai .env.production | Regenerate 64+ chars |
| `GEMINI_API_KEY=AIzaSyA7dgd...` | Thaolai .env.production | https://aistudio.google.com → API Keys |
| `TELEGRAM_BOT_TOKEN=8757840873:...` | brav os .env | @BotFather → /revoke |
| `GOOGLE_CLIENT_SECRET=GOCSPX-flo...` | brav os .env | GCP Console → OAuth 2.0 |
| `GOOGLE_REFRESH_TOKEN=1//0g...` | brav os .env | Re-run OAuth flow after client secret rotation |
| `SERPAPI_KEY=fdd041d57a...` | brav os .env | https://serpapi.com → Dashboard |
| `OPENCLAW_API_KEY=sk-or-v1-fa8...` | brav os .env | OpenRouter Dashboard → API Keys |
| `SUPABASE_DB_PASSWORD=RmgsKfDZ...` | brav os .env | Supabase → Project Settings → Database → Reset |

---

## Rotation Steps Per Secret

### 1. Thaolai DB_PASSWORD
```sql
-- Run on PostgreSQL server:
ALTER USER postgres PASSWORD 'NEW_STRONG_PASSWORD_HERE';
```
Then update `.env.production` → `DB_PASSWORD=NEW_STRONG_PASSWORD_HERE`

### 2. Thaolai JWT_SECRET
```bash
# Generate new 64-char secret:
openssl rand -hex 64
# Copy output → paste into .env.production JWT_SECRET=
```
> ⚠️ Rotating JWT_SECRET will invalidate ALL active user sessions → users must re-login

### 3. Thaolai GEMINI_API_KEY
1. Go to https://aistudio.google.com → API Keys
2. Delete current key
3. Create new key
4. Update `.env.production` → `GEMINI_API_KEY=`

### 4. Telegram Bot Token
```
In Telegram → @BotFather → /mybots → Select bot → API Token → Revoke
Copy new token → paste into .env
```

### 5. Google OAuth Client Secret
1. GCP Console → APIs & Services → Credentials
2. Click on your OAuth 2.0 Client → Edit
3. Reset Secret
4. Update `.env` → `GOOGLE_CLIENT_SECRET=`
5. Re-run OAuth flow to get new `GOOGLE_REFRESH_TOKEN`

### 6. Supabase DB Password
1. Supabase → Your Project → Project Settings → Database
2. Reset Database Password
3. Update all 3 DATABASE_URL values in `.env.production`

---

## After Rotating — Verification Checklist

- [ ] Thaolai API still boots: `curl https://thaolai.com/api/version`
- [ ] Thaolai LINE webhook works (send test message from LINE)
- [ ] Brav OS boots without STRICT_BOOTSTRAP errors
- [ ] New Telegram bot token responds to /start
- [ ] Google Workspace integration still works

---

## Generate Strong Secrets (PowerShell)

```powershell
# JWT Secret (64 chars hex)
[System.Web.Security.Membership]::GeneratePassword(64, 8)
# OR
-join (1..64 | ForEach { [char](Get-Random -Minimum 33 -Maximum 126) })

# Random password (32 chars)
[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
```

```bash
# Linux/Mac/WSL:
openssl rand -hex 32   # for passwords
openssl rand -hex 64   # for JWT secrets
openssl rand -base64 32  # for base64 secrets
```
