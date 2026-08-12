# GRAXIA-OS Infrastructure Setup Guide

Step-by-step guide to provision VPS infrastructure, install dependencies,
configure health checks, and set up standby failover.

**Quick-start checklist:** `docs/vps_deployment_checklist.md` — step-by-step checklist to follow during deployment.
**Budget comparison:** `docs/vps_budget_comparison.md` — cost comparison across VPS providers and risk analysis.
**Automated deploy:** `scripts/deploy_vps.ps1` — PowerShell script that automates Steps 1-6 of the checklist.

---

## 1. VPS Selection

### Primary VPS
| Property       | Recommendation                                  |
|----------------|--------------------------------------------------|
| Provider       | Contabo Windows VPS                             |
| Location       | London (LD4) — same metro as Pepperstone UK     |
| OS             | Windows Server 2019/2022                        |
| Specs          | 2 vCPU, 4 GB RAM, ~50 GB SSD minimum            |
| Cost           | Verify at checkout (~€5-8/month base + Windows license) |

XAUUSD M15 trading is not tick-sensitive. 15–30 ms latency is sufficient.

### Standby (Failover) VPS
| Property       | Recommendation                                  |
|----------------|--------------------------------------------------|
| Provider       | Different from primary (e.g. Hyonix, or Contabo Singapore) |
| OS             | Windows Server 2019/2022                        |
| Specs          | 1 vCPU, 2 GB RAM, ~30 GB SSD (minimal)          |
| Cost           | ~$5-10/month                                     |

The standby runs cold — it monitors the primary's heartbeat and only takes
over if the primary VPS is unresponsive for > 30 minutes.

---

## 2. RDP Setup

1. After provisioning, RDP into the VPS (Windows Remote Desktop).
2. Apply Windows updates: `Settings > Update & Security > Check for updates`
3. Set timezone to UTC: `Settings > Time & Language > Date & time`
4. Disable sleep: `Settings > System > Power & sleep > Never`
5. Create a dedicated folder: `C:\graxia-os`

---

## 3. MT5 Install + Pepperstone Login

1. Download MT5 from [Pepperstone's download page](https://pepperstone.com/en/trading-platforms/metatrader-5/)
2. Install to default path (`C:\Program Files\MetaTrader 5`)
3. Launch MT5, connect to Pepperstone demo account first:
   - File > Open an Account > Pepperstone > Demo
4. Once Phase 0-4 gates are cleared, open a live account (same broker menu)
5. Enable automated trading:
   - Tools > Options > Expert Advisors > Allow Automated Trading
   - Tools > Options > Expert Advisors > Allow DLL imports

---

## 4. Python Environment Setup

Install Python 3.10+ (the project targets Python >= 3.11):

```powershell
# Download from https://www.python.org/downloads/
# Or via winget:
winget install Python.Python.3.11

# Verify
python --version

# Install pip packages
python -m pip install --upgrade pip
pip install MetaTrader5 requests

# Clone the repo
git clone https://github.com/your-org/graxia-os.git C:\graxia-os
cd C:\graxia-os

# Install quant_os in editable mode
pip install -e graxia/packages/quant_os
```

**Use a deploy key, not your personal GitHub password:**
1. Generate a key on the VPS: `ssh-keygen -t ed25519 -C "vps-primary"`
2. Add the public key to the repo's Deploy Keys (Settings > Deploy Keys)
3. Clone via SSH: `git clone git@github.com:your-org/graxia-os.git`

---

## 5. Repo Clone with Deploy Key

```powershell
# On VPS
ssh-keygen -t ed25519 -C "vps-primary" -f $env:USERPROFILE\.ssh\vps_primary
type $env:USERPROFILE\.ssh\vps_primary.pub

# Copy the output and add as a Deploy Key on GitHub:
#   Repo > Settings > Deploy Keys > Add deploy key
#   Title: "Primary VPS", Allow write access: No

# Clone
git clone git@github.com:your-org/graxia-os.git C:\graxia-os
```

---

## 6. Windows Task Scheduler Auto-Start Config

Run the setup script as Administrator:

```powershell
# In PowerShell (Run as Administrator):
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
cd C:\graxia-os\graxia\packages\quant_os
.\scripts\setup_scheduler.ps1 -PythonPath "C:\Python311\python.exe"
```

This creates two scheduled tasks:
- **GRAXIA-OS Bot**: Runs `webhook.py --live` at system startup
- **GRAXIA-OS HealthCheck**: Runs `monitoring/health_check.py` at system startup

Verify tasks are created:
```powershell
Get-ScheduledTask -TaskName "GRAXIA-OS*" | Format-Table TaskName, State
```

---

## 7. Standby VPS Setup

Repeat the same steps on the standby VPS with these differences:

1. Use a **different provider** (or different datacenter)
2. Set environment variable on standby:
   ```powershell
   [Environment]::SetEnvironmentVariable("STANDBY_MODE", "watch_only", "Machine")
   ```
3. The standby's webhook.py should run in watch-only mode:
   - It monitors the same MT5 account
   - It does **not** place orders unless it receives a `POST /takeover` from the primary
   - Implement a small Flask/FastAPI listener on port 8000 for the `/takeover` endpoint
4. Do **not** schedule the primary health check on the standby — the standby has its own internal self-check

### Standby `/takeover` Endpoint (lightweight)

```python
# standby_listener.py — run this alongside webhook.py on the standby VPS
from fastapi import FastAPI
import os

app = FastAPI()
STANDBY_SECRET = os.getenv("STANDBY_SECRET", "change-me")

@app.post("/takeover")
async def takeover():
    # Verify shared secret from X-Standby-Secret header
    # Flip environment flag so webhook.py starts placing orders
    os.environ["STANDBY_MODE"] = "active"
    return {"status": "activated"}
```

---

## 8. Health Check as Separate Scheduled Task

The health check process (`monitoring/health_check.py`) is registered as a
separate task by the setup script. It runs independently of `webhook.py`:

```
Schedule: At startup (runs when system boots, whether user is logged on or not)
Process:  monitoring/health_check.py
Logic:    Checks data/heartbeat.txt every 300 seconds
           - 15 min stale → restart webhook.py locally
           - 30 min stale → POST to standby VPS takeover endpoint
```

Monitor it:
```powershell
Get-ScheduledTask -TaskName "GRAXIA-OS HealthCheck" | Get-ScheduledTaskInfo
```

---

## 9. Testing Checklist

Run through each item before declaring infrastructure ready:

- [ ] Primary VPS: RDP accessible
- [ ] Primary VPS: MT5 installed, Pepperstone demo account connected
- [ ] Primary VPS: Python 3.11+ installed, `pip list` shows MetaTrader5 and requests
- [ ] Primary VPS: Repo cloned to `C:\graxia-os`
- [ ] Primary VPS: `scripts/telegram_config.toml` populated with real bot token + chat ID
- [ ] Primary VPS: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` env vars set (or config file present)
- [ ] Primary VPS: `STANDBY_WEBHOOK_URL` env var set
- [ ] Telegram: `/start` your bot, verify you can receive messages
- [ ] Primary VPS: Run `python scripts/telegram_monitor.py` — confirm a test message arrives
- [ ] Primary VPS: Task Scheduler entries created (verify with `Get-ScheduledTask`)
- [ ] Primary VPS: Reboot VPS, verify both tasks auto-start (`Get-ScheduledTaskInfo`)
- [ ] Primary VPS: Delete `data/heartbeat.txt`, wait 5 min, verify health check sends alert
- [ ] Standby VPS: RDP accessible
- [ ] Standby VPS: Same stack installed, MT5 connected in watch-only mode
- [ ] Standby VPS: Standby listener running on port 8000, `/takeover` endpoint reachable from primary
- [ ] Standby VPS: Shared secret configured and matches primary's `STANDBY_SECRET`
- [ ] Failover drill: Stop `webhook.py` on primary, wait 30+ min, verify standby activates and sends failover alert
- [ ] Failover drill: Verify standby does NOT place orders until takeover is called
- [ ] Confirm Telegram receives: trade opened, trade closed, risk alert, heartbeat, failover messages
- [ ] Confirm alert_level filtering works (set to `critical`, verify non-critical messages are suppressed)

---

## 10. Environment Variables Summary

| Variable              | Required | Description                                   |
|-----------------------|----------|-----------------------------------------------|
| `TELEGRAM_BOT_TOKEN`  | Yes      | Telegram bot token from @BotFather             |
| `TELEGRAM_CHAT_ID`    | Yes      | Chat ID from @userinfobot                      |
| `STANDBY_WEBHOOK_URL` | Yes      | Standby VPS takeover endpoint URL               |
| `STANDBY_SECRET`      | Yes      | Shared secret for standby takeover auth         |
| `STANDBY_MODE`        | Yes      | Set to `watch_only` on standby VPS              |
| `ALERT_LEVEL`         | No       | info / warning / critical (default: info)       |
