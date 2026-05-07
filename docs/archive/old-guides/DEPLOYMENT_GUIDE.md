# 🚀 Graxia OS - Ultimate Free Stack Deployment Guide

> **ฟรี 100%** - Production-ready deployment using Fly.io, Supabase, Upstash, Vercel, and GitHub Actions

## 📋 Overview

| Service | Purpose | Free Tier Limit |
|---------|---------|----------------|
| **Fly.io** | Backend API + Workers | 3 VMs (256MB each) |
| **Supabase** | PostgreSQL Database | 500MB storage |
| **Upstash** | Redis + Queue | 10k commands/day |
| **Vercel** | Frontend | 100GB bandwidth |
| **GitHub Actions** | Cron jobs | Unlimited (public repo) |
| **Cloudflare** | DNS + CDN | Unlimited |

**Estimated capacity**: 100-500 active users before needing to upgrade

---

## 🎯 Prerequisites

- [ ] GitHub account (public repo)
- [ ] Fly.io account (need credit card for verification, but free tier is free)
- [ ] Supabase account
- [ ] Upstash account
- [ ] Vercel account
- [ ] Domain (optional, can use free domains)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│        Cloudflare (DNS + CDN)           │
│         your-domain.com                 │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│           Vercel (Frontend)             │
│    graxia-frontend.vercel.app          │
│    Static site + Dashboard             │
└─────────────┬───────────────────────────┘
              │ API Calls
              ▼
┌─────────────▼───────────────────────────┐
│          Fly.io (Backend)               │
│    VM 1: graxia-api (FastAPI)           │
│    VM 2: graxia-worker (Celery)        │
│    Region: Singapore (sin)              │
└──────┬──────────────────────────────────┘
       │
┌──────┴──────────────────────────────────┐
│              Data Layer                 │
│  ┌─────────────┐    ┌────────────────┐ │
│  │  Supabase   │    │   Upstash      │ │
│  │  Postgres   │    │   Redis        │ │
│  │  Port 6543  │    │   Queue        │ │
│  └─────────────┘    └────────────────┘ │
└─────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│          Background Jobs                │
│  GitHub Actions → Cron (15 min)        │
│  GitHub Actions → Daily report           │
│  QStash → Delayed tasks (optional)       │
└─────────────────────────────────────────┘
```

---

## 🛠️ Step-by-Step Setup

### Step 1: Create Accounts

1. **GitHub**: https://github.com (if not already)
2. **Fly.io**: https://fly.io (verify with credit card - no charge)
3. **Supabase**: https://supabase.com
4. **Upstash**: https://upstash.com
5. **Vercel**: https://vercel.com
6. **Cloudflare**: https://cloudflare.com (optional, for custom domain)

---

### Step 2: Setup Supabase (Database)

```bash
1. Go to https://supabase.com
2. Click "New Project"
3. Name: graxia-os
4. Region: Singapore (Southeast Asia)
5. Password: Use strong password, save it!
6. Wait 2-3 minutes for provisioning

7. Go to Settings → Database
8. Copy connection string for Transaction Mode (port 6543)
   Format: postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:6543/postgres

9. Save this - you'll need it for DATABASE_URL
```

---

### Step 3: Setup Upstash (Redis)

```bash
1. Go to https://console.upstash.com
2. Click "Create Database"
3. Name: graxia-redis
4. Region: Singapore
5. Type: Redis

6. Copy the REDIS_URL
   Format: redis://default:[PASSWORD]@[ENDPOINT]:6379

7. Also create QStash (in same console):
   - Name: graxia-queue
   - Copy QSTASH_TOKEN and QSTASH_URL
```

---

### Step 4: Setup Fly.io Apps

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Create apps
cd backend

# Create API app
flyctl apps create graxia-api

# Create Worker app
flyctl apps create graxia-worker

# Verify
echo "Apps created:"
flyctl apps list | grep graxia
```

---

### Step 5: Configure Environment

```bash
# Copy template
cd backend
cp .env.flyio-template .env

# Edit .env with your actual values
# Required:
# - DATABASE_URL (Supabase port 6543)
# - DATABASE_MIGRATION_URL (Supabase port 5432)
# - REDIS_URL (Upstash)
# - SECRET_KEY (openssl rand -hex 32)
# - ENCRYPTION_KEY (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# - INTERNAL_API_KEY (openssl rand -hex 32)
# - OPENAI_API_KEY (or your LLM provider)
# - SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
# - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# - RESEND_API_KEY (optional, for email)
```

**Set secrets to Fly.io:**
```bash
cd backend

# Set all secrets from .env file
while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    key=$(echo "$line" | cut -d= -f1)
    value=$(echo "$line" | cut -d= -f2-)
    [[ "$value" == "" ]] && continue
    echo "Setting $key..."
    flyctl secrets set --app graxia-api "$key=$value"
done < .env

# Same for worker
while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    key=$(echo "$line" | cut -d= -f1)
    value=$(echo "$line" | cut -d= -f2-)
    [[ "$value" == "" ]] && continue
    flyctl secrets set --app graxia-worker "$key=$value"
done < .env
```

---

### Step 6: Deploy to Fly.io

```bash
# Deploy API
cd backend
flyctl deploy --config fly.toml --remote-only

# Deploy Worker (in another terminal or after API is done)
flyctl deploy --config fly.worker.toml --remote-only

# Verify
flyctl status --app graxia-api
flyctl status --app graxia-worker

# Check logs
flyctl logs --app graxia-api
```

---

### Step 7: Setup GitHub Secrets

Go to your GitHub repo → Settings → Secrets and variables → Actions

Add these secrets:

```
GRAXIA_API_URL=https://graxia-api.fly.dev
INTERNAL_API_KEY=(same as in .env)
FLY_API_TOKEN=(flyctl tokens create)
```

**Get FLY_API_TOKEN:**
```bash
flyctl tokens create
```

---

### Step 8: Update Vercel Frontend

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

Push to GitHub, Vercel will redeploy automatically.

---

### Step 9: Setup Cloudflare (Optional)

```bash
1. Add your domain to Cloudflare
2. Change nameservers at your registrar
3. Create DNS record:
   - Type: CNAME
   - Name: api
   - Target: graxia-api.fly.dev
   - Proxy status: DNS only (gray cloud)
   
4. For frontend:
   - Type: CNAME
   - Name: @ or www
   - Target: your-frontend.vercel.app
   - Proxy status: Proxied (orange cloud) for CDN
```

---

## 🧪 Testing

### Test API Health
```bash
curl https://graxia-api.fly.dev/health
```

### Test Database Connection
```bash
curl https://graxia-api.fly.dev/api/v1/system/health
```

### Trigger Lead Hunter Manually
```bash
curl -X POST https://graxia-api.fly.dev/api/v1/internal/run-lead-hunter \
  -H "Authorization: Bearer YOUR_INTERNAL_API_KEY"
```

---

## 📊 Monitoring Limits

| Service | Current | Limit | Status |
|---------|---------|-------|--------|
| Supabase Storage | Check in dashboard | 500MB | ⚠️ Monitor weekly |
| Upstash Commands | Check in dashboard | 10k/day | ⚠️ Monitor daily |
| Fly.io VMs | 2 of 3 used | 3 VMs | ✅ OK |
| GitHub Actions | Check repo insights | Unlimited | ✅ OK |

---

## 🚨 Troubleshooting

### Database Connection Errors
```bash
# Check if using port 6543 (Transaction mode)
flyctl secrets list --app graxia-api | grep DATABASE_URL

# Should contain :6543 not :5432
```

### Worker Not Processing Jobs
```bash
# Check worker logs
flyctl logs --app graxia-worker

# Restart if needed
flyctl restart --app graxia-worker
```

### API Returns 502
```bash
# Check if app is running
flyctl status --app graxia-api

# Check logs
flyctl logs --app graxia-api

# Redeploy if needed
flyctl deploy --config fly.toml --remote-only
```

---

## 🔐 Security Checklist

- [ ] SECRET_KEY is 64+ characters
- [ ] ENCRYPTION_KEY is set (32 bytes base64)
- [ ] INTERNAL_API_KEY is set (for cron jobs)
- [ ] Redis URLs have strong passwords
- [ ] TELEGRAM_BOT_TOKEN is valid
- [ ] CORS_ORIGINS set to production domains only
- [ ] APP_ENV=production

---

## 💰 When to Upgrade

| Scenario | Action | Cost |
|----------|--------|------|
| Supabase 500MB full | Upgrade to Pro | $25/mo |
| Upstash 10k commands/day | Upgrade | $10/mo |
| Fly.io need more VMs | Upgrade or move to Hostinger | $5-8/mo per VM |
| Need more workers | Upgrade or Hostinger VPS | $8/mo |

**Recommended upgrade path**: Fly.io → Hostinger KVM 2 ($8/mo) when you outgrow free tier

---

## 📞 Support

- Fly.io: https://community.fly.io
- Supabase: https://github.com/supabase/supabase/discussions
- Upstash: https://upstash.com/support
- Graxia OS: Open GitHub issue

---

**Status**: Ready for production deployment ✅
