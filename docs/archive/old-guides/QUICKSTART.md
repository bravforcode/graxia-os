# 🚀 Graxia OS - Quick Start (5 Minute Setup)

## Prerequisites
- GitHub account
- Fly.io account (verify with credit card - no charge)
- Supabase account
- Upstash account
- Vercel account

## 5-Minute Setup

### 1. Create Infrastructure (2 minutes)

```bash
# Supabase
# - Create project at https://supabase.com
# - Region: Singapore
# - Save password and connection string (port 6543)

# Upstash
# - Create Redis at https://console.upstash.com
# - Region: Singapore
# - Copy REDIS_URL

# Fly.io (install if needed)
curl -L https://fly.io/install.sh | sh
flyctl auth login

# Create apps
cd backend
flyctl apps create graxia-api
flyctl apps create graxia-worker
```

### 2. Configure Environment (2 minutes)

```bash
# Copy template
cp .env.flyio-template .env

# Edit .env with your actual values:
# - DATABASE_URL (Supabase port 6543)
# - REDIS_URL (Upstash)
# - SECRET_KEY (openssl rand -hex 32)
# - ENCRYPTION_KEY (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# - INTERNAL_API_KEY (openssl rand -hex 32)
# - OPENAI_API_KEY or LLM provider key
# - SUPABASE_URL and keys
# - TELEGRAM_BOT_TOKEN and CHAT_ID
```

### 3. Deploy (1 minute)

```bash
# Run complete setup script
cd ..
./scripts/setup-complete.sh

# Or manually:
flyctl deploy --config fly.toml
flyctl deploy --config fly.worker.toml
```

### 4. Setup GitHub Secrets (1 minute)

Go to GitHub repo → Settings → Secrets → Actions:

```
GRAXIA_API_URL=https://graxia-api.fly.dev
INTERNAL_API_KEY=<from .env>
FLY_API_TOKEN=<flyctl tokens create>
```

### 5. Update Vercel

```json
// vercel.json
{
  "rewrites": [
    {
      "source": "/api/(.*)",
      "destination": "https://graxia-api.fly.dev/api/$1"
    },
    {
      "source": "/((?!api/).*)",
      "destination": "/index.html"
    }
  ]
}
```

Push to GitHub. Done! 🎉

---

## Verify

```bash
# Test health
curl https://graxia-api.fly.dev/health

# Check status
flyctl status --app graxia-api
flyctl logs --app graxia-api
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 502 error | `flyctl logs --app graxia-api` |
| DB error | Check port 6543 in DATABASE_URL |
| Worker not running | `flyctl restart --app graxia-worker` |
| Cron not working | Check GitHub Actions logs |

---

## Costs

**All services are FREE for 100-500 users:**
- Fly.io: 3 VMs (256MB) = $0
- Supabase: 500MB = $0
- Upstash: 10k commands/day = $0
- Vercel: 100GB bandwidth = $0
- GitHub Actions: Unlimited = $0

**Upgrade when:**
- Supabase > 500MB → $25/mo
- Upstash > 10k commands → $10/mo
- Need more VMs → Hostinger KVM 2 ($8/mo)
