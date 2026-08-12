# Bridge State — AWS + VPS Container Deployment
**Date**: 2026-06-26 17:02 UTC
**Status**: Infrastructure deployed, source code pending

## Architecture
```
┌─ VPS 27.254.134.59 (Debian 12) ───────────────────────────┐
│  Existing: 26 containers (thaolai.com production)          │
│  New: graxia-trading-net (172.22.0.0/24) — ZERO overlap    │
│                                                             │
│  Container 1: graxia-db (postgres:16-alpine)               │
│    - Internal: 172.22.0.10:5432                             │
│    - No host port (internal only)                           │
│    - Resource: 1 CPU / 2GB RAM                             │
│                                                             │
│  Container 2: graxia-api (FastAPI)                         │
│    - Host port: 8751 → internal 8000                       │
│    - Serves signals to MT5 bot                             │
│    - Resource: 1.5 CPU / 1.5GB RAM                        │
│    - Read-only root, non-root user                         │
│                                                             │
│  Container 3: graxia-trainer (XGBoost auto-retrain)        │
│    - No ports exposed                                      │
│    - Supercronic cron: train @ 02:00 UTC                   │
│    - Resource: 4 CPU / 6GB RAM                            │
└──────────────────────────────────────────────────────────┘

┌─ AWS Free Tier (Windows t2.micro) ─────────────────────────┐
│  MT5 (headless via NSSM service) + paper_trade_bot.py      │
│  Connects to graxia-api:8751 for signals                   │
└──────────────────────────────────────────────────────────┘
```

## Files Deployed to VPS (/opt/graxia-trading/)
- `docker-compose.yml` — complete compose with 3 services
- `docker/Dockerfile.api` — FastAPI multi-stage build
- `docker/Dockerfile.trainer` — XGBoost trainer with supercronic
- `docker/db/init.sql` — PostgreSQL schema (trades, signals, training_runs)
- `docker/trainer/crontab` — scheduled retrain every 02:00 UTC
- `docker/trainer/entrypoint-trainer.sh` — initial train + supercronic
- `docker/requirements.api.txt` — pinned deps for API
- `docker/requirements.trainer.txt` — pinned deps for trainer
- `.env.example` — template with auto-generated secrets
- `scripts/deploy_vps.sh` — one-time deploy script

## Local Files Created (quant_os project)
- `docker-compose.yml` — same as VPS
- `docker/` — all Dockerfile + config
- `scripts/deploy_vps.sh` — VPS deploy
- `scripts/setup_aws_bot.ps1` — AWS Windows setup
- `scripts/sync_to_vps.sh` — sync helper

## How to Deploy
1. **Transfer source**: From PowerShell on your machine:
   ```powershell
   tar czf - --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' `
     -C "C:\Users\menum\graxia os\graxia\packages\quant_os" . | `
     ssh root@27.254.134.59 "tar xzf - -C /opt/graxia-trading/quant_os"
   ```

2. **SSH to VPS + deploy**:
   ```bash
   cd /opt/graxia-trading && bash scripts/deploy_vps.sh
   ```

3. **Create AWS instance + run** `setup_aws_bot.ps1`

## Security Checklist (read from auditor report)
- ❗ P0.1: PostgreSQL exposed to 0.0.0.0:5432 — ADD `listen_addresses = '127.0.0.1'`
- ❗ P0.2: Root SSH with password — ADD SSH key, disable PasswordAuthentication
- ❗ P0.3: Set Docker resource limits on trading containers (done)
- ❗ P0.4: Only port 8751 exposed for graxia-api
