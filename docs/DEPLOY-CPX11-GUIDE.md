# GRAXIA OS - Deploy Guide for Hetzner CPX11 (2GB RAM)

## Overview

This guide deploys GRAXIA OS on **Hetzner CPX11** (2 vCPU, 2GB RAM, 40GB SSD) - the most cost-effective production setup at **€4.51/month (~180 THB)**.

### Memory Budget (2GB Total)

| Service               | Memory Limit | Purpose                    |
| --------------------- | ------------ | -------------------------- |
| Caddy (Reverse Proxy) | 64MB         | HTTPS/SSL termination      |
| Backend API           | 512MB        | FastAPI application        |
| Worker                | 512MB        | Celery background tasks    |
| Beat (Scheduler)      | 128MB        | Cron job scheduler         |
| Redis                 | 384MB        | Cache & task queue         |
| Promtail              | 64MB         | Log shipping (optional)    |
| **Total**             | **~1664MB**  | **~336MB reserved for OS** |

### Architecture

```
Internet
    |
    ▼
  Caddy (:80/:443) ──► Backend API (:8000)
                            │
                            ├── Redis (cache + queue)
                            ├── Celery Worker
                            └── Celery Beat (scheduler)

Supabase (free tier) ──► PostgreSQL Database
Vercel (free tier)   ──► Frontend (React + Bun)
```

---

## Prerequisites

1. **Hetzner Cloud Account** - [Sign up](https://www.hetzner.com/cloud)
2. **Domain Name** - Point to VPS IP
3. **GitHub Account** - For Vercel frontend (optional)
4. **Supabase Account** - Database (free tier)

---

## Step 1: Create VPS

### Hetzner Console

1. Create new project
2. Add server → Location: Singapore or Germany
3. Select **CPX11** (2 vCPU, 2GB RAM, 40GB NVMe)
4. Image: **Ubuntu 22.04**
5. Add SSH key (generate with `ssh-keygen`)
6. Firewall: Allow ports 22, 80, 443
7. Create & wait 1-2 minutes

### Connect via SSH

```bash
ssh root@YOUR-VPS-IP
```

---

## Step 2: System Setup

```bash
# Update system
apt update && apt upgrade -y

# Install essential packages
apt install -y curl wget git htop nano ufw fail2ban

# Configure firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Install Docker Compose
apt install -y docker-compose-plugin

# Create user for deployment
useradd -m -s /bin/bash graxia
usermod -aG docker graxia

# Setup swap (critical for 2GB RAM)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Optimize for low memory
cat >> /etc/sysctl.conf << 'EOF'
vm.swappiness=10
vm.overcommit_memory=1
vm.vfs_cache_pressure=50
EOF
sysctl -p
```

---

## Step 3: Deploy GRAXIA OS

```bash
# Switch to graxia user
su - graxia

# Clone repository
git clone https://github.com/your-username/graxia-os.git
cd graxia-os

# Copy environment template
cp .env.cpx11.template .env.production

# Edit environment variables
nano .env.production
```

### Required Changes in .env.production:

```bash
# Your domain (point DNS A record to VPS IP)
APP_HOST=your-domain.com
APP_BASE_URL=https://your-domain.com
FRONTEND_URL=https://your-domain.com

# Supabase credentials
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DATABASE_URL=postgresql://...

# AI API keys (at least one)
GEMINI_API_KEY=your-gemini-key
# or
OPENCLAW_API_KEY=your-openrouter-key

# Telegram for alerts (optional)
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

### Deploy

```bash
# Make scripts executable
chmod +x deploy/scripts/*.sh

# Run deployment
./deploy/scripts/deploy-cpx11.sh deploy
```

This will:

- ✅ Optimize system for 2GB RAM
- ✅ Setup 2GB swap
- ✅ Deploy all services with memory limits
- ✅ Configure auto-start on boot
- ✅ Setup memory monitoring
- ✅ Verify deployment

---

## Step 4: Configure Domain & SSL

### DNS Setup

```
Type: A
Name: @ (or api)
Value: YOUR-VPS-IP
TTL: 3600
```

### Update Caddyfile

```bash
nano deploy/Caddyfile.cpx11
```

Replace `YOUR_DOMAIN` with your actual domain:

```
your-domain.com {
    reverse_proxy backend:8000

    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }

    encode zstd gzip
}
```

Restart:

```bash
docker compose -f docker-compose.cpx11.yml restart caddy
```

---

## Step 5: Frontend Deployment (Vercel + Bun)

### Option A: Vercel (Recommended - Free + Fast CDN)

```bash
# 1. Push frontend/ to GitHub
# 2. Import repo to Vercel
# 3. Set build command: bun run build
# 4. Set output directory: dist
# 5. Add environment variables:
VITE_API_BASE_URL=https://your-domain.com/api/v1
VITE_SUPABASE_URL=your-supabase-url
VITE_SUPABASE_ANON_KEY=your-anon-key
```

### Option B: Static on VPS (Saves Vercel slot)

```bash
# Build locally with Bun
cd frontend
bun install
bun run build

# Upload dist/ to VPS
scp -r dist/ root@your-vps-ip:/root/graxia-os/frontend/dist/

# Add to Caddyfile:
your-domain.com {
    root * /var/www/frontend/dist
    file_server
    try_files {path} /index.html

    # API proxy
    handle /api/* {
        reverse_proxy backend:8000
    }

    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
    }

    encode zstd gzip
    tls your-email@example.com
}
```

---

## Management Commands

### Check Status

```bash
./deploy/scripts/deploy-cpx11.sh status
```

### View Logs

```bash
# All logs
./deploy/scripts/deploy-cpx11.sh logs

# Specific service
./deploy/scripts/deploy-cpx11.sh logs backend
./deploy/scripts/deploy-cpx11.sh logs worker
./deploy/scripts/deploy-cpx11.sh logs redis
```

### Monitor Resources

```bash
# Real-time monitoring
./deploy/scripts/deploy-cpx11.sh monitor

# Or use htop
htop
```

### Manual Container Commands

```bash
# Container status
docker compose -f docker-compose.cpx11.yml ps

# View stats
docker stats --no-stream

# Restart specific service
docker compose -f docker-compose.cpx11.yml restart backend

# Update to latest
docker compose -f docker-compose.cpx11.yml pull
docker compose -f docker-compose.cpx11.yml up -d --remove-orphans
```

---

## Monitoring & Alerts

### Memory Alerts

The system automatically monitors memory every 5 minutes. If usage exceeds 85%, it will:

1. Log to `/var/log/graxia/memory-alerts.log`
2. Send Telegram notification (if configured)
3. Optionally restart worker service

### Health Checks

```bash
# Check API health
curl https://your-domain.com/health

# Check all services
docker compose -f docker-compose.cpx11.yml ps
```

### View Resource Usage

```bash
# Container stats
docker stats --no-stream

# Memory breakdown
./deploy/scripts/deploy-cpx11.sh status
```

---

## Troubleshooting

### High Memory Usage (>90%)

```bash
# Emergency optimization
./deploy/scripts/memory-optimizer.sh

# Check what's using memory
docker stats --no-stream

# Restart heaviest service
docker compose -f docker-compose.cpx11.yml restart worker
```

### Service Won't Start

```bash
# Check logs
docker compose -f docker-compose.cpx11.yml logs [service]

# Common issues:
# 1. Memory limit too low → increase in docker-compose.cpx11.yml
# 2. Missing env vars → check .env.production
# 3. Port conflict → check with: netstat -tlnp
```

### Redis OOM

```bash
# If Redis memory full
docker compose -f docker-compose.cpx11.yml exec redis redis-cli
> INFO memory
> FLUSHDB  # Clear all (emergency only)
> exit
```

### Swap Full

```bash
# Check swap usage
swapon --show
free -h

# Clear swap (only if memory available)
swapoff -a && swapon -a
```

---

## Backup Strategy

### Automated Daily Backup

```bash
# Add to crontab
crontab -e

# Add line:
0 2 * * * cd ~/graxia-os && docker compose -f docker-compose.cpx11.yml exec -T backend python -m app.cli backup create --name "auto-$(date +\%Y\%m\%d)" >> logs/backup.log 2>&1
```

### Manual Backup

```bash
# Database (via Supabase dashboard)
# Redis
docker compose -f docker-compose.cpx11.yml exec redis redis-cli SAVE
docker cp $(docker compose -f docker-compose.cpx11.yml ps -q redis):/data/dump.rdb ./backups/redis-$(date +%Y%m%d).rdb
```

---

## Step 6: Automated Deployment (GitHub Actions)

### Setup GitHub Secrets

Go to **Settings → Secrets and variables → Actions**:

| Secret            | Value                       |
| ----------------- | --------------------------- |
| `HEZTNER_HOST`    | Your VPS IP address         |
| `HEZTNER_USER`    | `root` or deployment user   |
| `HEZTNER_SSH_KEY` | Private key (full contents) |

### Workflow

Already configured at `.github/workflows/deploy-cpx11.yml`. Every push to `main` or `production` branch will:

1. Build frontend with Bun
2. Build and push Docker image to GitHub Container Registry
3. Deploy to Hetzner via SSH
4. Verify health check
5. Auto-rollback on failure

### Manual Trigger

```bash
# Go to Actions tab → Deploy to Hetzner CPX11 → Run workflow
```

---

## Architecture Summary

```
┌─────────────────────────────────────────────┐
│          Internet / CDN (Vercel)            │
│              Frontend (React+Bun)           │
│              https://your-domain.com         │
└──────────────────┬──────────────────────────┘
                   │ API calls
┌──────────────────▼──────────────────────────┐
│         Hetzner CPX11 (€4.51/mo)           │
│                                             │
│  ┌─────────┐    ┌───────────────────────┐ │
│  │ Caddy   │───►│ FastAPI Backend       │ │
│  │ 64MB    │    │ 512MB                 │ │
│  │ SSL+RP  │    │ API + Auth + Revenue  │ │
│  └─────────┘    └───────────────────────┘ │
│                        │                    │
│       ┌────────────────┼────────────────┐   │
│       ▼                ▼                ▼  │
│  ┌────────┐      ┌──────────┐      ┌─────┐│
│  │ Redis  │      │ Celery   │      │ Beat││
│  │ 384MB  │      │ Worker   │      │ 128 ││
│  │ Cache+ │      │ 512MB    │      │ MB  ││
│  │ Queue  │      └──────────┘      └─────┘│
│  └────────┘                                 │
└─────────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│      Supabase (Free Tier)                   │
│      PostgreSQL Database                    │
│      https://supabase.com                   │
└─────────────────────────────────────────────┘
```

### Why This Architecture?

- **Vercel Frontend**: CDN edge caching, free tier, Bun builds in ~3s
- **CPX11 Backend**: €4.51/mo, runs everything needed, 2GB is enough with limits
- **Supabase DB**: Free tier, managed PostgreSQL, no DB maintenance on VPS
- **Redis on VPS**: Zero latency queue/cache, avoids Supabase connection limits
- **Caddy**: Auto HTTPS, memory efficient (64MB), zero config SSL

### Memory Breakdown (Verified)

| Service   | Limit      | Actual     | Safe                   |
| --------- | ---------- | ---------- | ---------------------- |
| Caddy     | 64MB       | ~20MB      | ✅                     |
| Backend   | 512MB      | ~250MB     | ✅                     |
| Worker    | 512MB      | ~200MB     | ✅                     |
| Beat      | 128MB      | ~50MB      | ✅                     |
| Redis     | 384MB      | ~150MB     | ✅                     |
| Promtail  | 64MB       | ~20MB      | ✅                     |
| **Total** | **1664MB** | **~710MB** | **✅ 1030MB headroom** |

---

## Scaling Up

When you outgrow CPX11 (2GB), upgrade path:

### Option 1: CPX21 (4GB) - Double Resources

```
€8.91/month → 4 vCPU, 4GB RAM, 80GB SSD
Just change docker-compose memory limits
```

### Option 2: Separate Worker Server

```
VPS 1 (CPX11): API + Redis
VPS 2 (CPX11): Workers only
```

### Option 3: Managed Services

```
Redis: Upstash (free tier)
Workers: Fly.io (scale independently)
```

---

## Cost Summary

| Item          | Cost               | Notes               |
| ------------- | ------------------ | ------------------- |
| Hetzner CPX11 | €4.51 (~180 THB)   | 2GB RAM, 24/7       |
| Domain        | ~300 THB/year      | ~25 THB/month       |
| Supabase      | Free               | Existing tier       |
| **Total**     | **~205 THB/month** | Full 24/7 operation |

---

## Support

If issues occur:

1. Check logs: `./deploy/scripts/deploy-cpx11.sh logs`
2. Check memory: `./deploy/scripts/deploy-cpx11.sh status`
3. Run optimizer: `./deploy/scripts/memory-optimizer.sh`
4. Restart: `./deploy/scripts/deploy-cpx11.sh restart`

---

**🎉 You now have GRAXIA OS running 24/7 on €4.51/month!**
