# GRAXIA-OS VPS Deployment Checklist

## Primary: Contabo Windows VPS (London LD4)
## Standby: Hyonix Windows VPS (Singapore)

---

### Step 1: Order & Provision (30 min)

- [ ] Order Windows VPS from Contabo (London LD4)
- [ ] Note: Contabo pricing ~€5-6/month for Windows VPS S (2 vCPU, 4 GB RAM, 50 GB SSD)
- [ ] Wait for provisioning email (usually 1-2h)
- [ ] Order standby VPS from Hyonix (Singapore) — different provider, different geography
- [ ] Note IP addresses for both
- [ ] Set RDP password for both (strong, unique, store in password manager)

### Step 2: Initial RDP Setup (30 min)

- [ ] Connect via Remote Desktop (`mstsc` / Windows Remote Desktop Connection)
- [ ] Run Windows Update → install all updates → reboot
- [ ] Reboot and repeat until no updates remain
- [ ] Set timezone to UTC: Settings > Time & Language > Date & time
- [ ] Disable sleep/hibernation: Settings > System > Power & sleep > Never
- [ ] Disable screensaver (or set to blank, 999 min)
- [ ] Install Google Chrome (for MT5 web terminal / monitoring)
- [ ] Install Notepad++ (for config editing)
- [ ] Create folder structure: `C:\graxia-os` and `C:\graxia-env`
- [ ] Windows Defender: add exclusions for `C:\graxia-os` and `C:\graxia-env` to avoid scan interference
- [ ] (Optional) Open TCP 8000 in Windows Firewall for health check listener if cross-VPS comms needed

### Step 3: Install MT5 (15 min)

- [ ] Download Pepperstone MT5 from pepperstone.com/en/trading-platforms/metatrader-5/
- [ ] Install to default path (`C:\Program Files\MetaTrader 5`)
- [ ] Launch → File → Open an Account → Pepperstone → Demo
- [ ] Connect Demo account 61547941
- [ ] Verify XAUUSD symbol loads (Market Watch → right-click → Symbols → XAUUSD enabled)
- [ ] Verify spread displayed (15-25 pts expected for Razor ECN)
- [ ] Enable automated trading: Tools → Options → Expert Advisors → Allow Automated Trading (check)
- [ ] Also enable: Allow DLL imports
- [ ] Keep MT5 running (minimize to tray, never close)
- [ ] Note: MT5 must stay open — the Python MetaTrader5 package connects to the running terminal

### Step 4: Install Python Environment (20 min)

- [ ] Download Python 3.11.14 from python.org (Windows installer 64-bit)
- [ ] Run installer → check "Add Python to PATH" → Install
- [ ] Open PowerShell as Administrator:

```powershell
python --version
# Must show Python 3.11.14

# Create virtual environment
python -m venv C:\graxia-env
C:\graxia-env\Scripts\Activate.ps1
# Prompt should show (graxia-env)

# Clone repo (HTTPS for simplicity; deploy key for production)
git clone https://github.com/bravforcode/graxia-os.git C:\graxia-os

# Install packages
pip install --upgrade pip
cd C:\graxia-os\graxia\packages\quant_os
pip install -r requirements.txt

# Set env var (prevents UnicodeEncodeError on cp1252 terminals)
[System.Environment]::SetEnvironmentVariable('PYTHONIOENCODING','utf-8','Machine')

# Verify MT5 bindings
python -c "import MetaTrader5; print('MT5 OK:', MetaTrader5.__version__)"
```

### Step 5: Configure & Test (20 min)

- [ ] Copy config template:

```powershell
cd C:\graxia-os\graxia\packages\quant_os
copy scripts\telegram_config.toml scripts\telegram_config.toml.bak
```

- [ ] Edit `scripts\telegram_config.toml` with real bot token and chat ID
- [ ] Verify Telegram: `python -c "from core.telegram_notify import TelegramNotifier; TelegramNotifier().send('VPS setup test')"`
- [ ] Test MT5 connection: `python scripts/mt5_verify.py`
- [ ] Run trial walk-forward (quick test, not full run): `python scripts/walk_forward.py --symbol XAUUSD --freq 15min --n-trials 5`
- [ ] Test health check starts: `python -m monitoring.health_check` (should print startup message)
- [ ] Set environment variables (or rely on .env / config files):

```powershell
[System.Environment]::SetEnvironmentVariable('STANDBY_WEBHOOK_URL','http://<standby-ip>:8000/takeover','Machine')
[System.Environment]::SetEnvironmentVariable('STANDBY_SECRET','<shared-secret>','Machine')
```

### Step 6: Setup Auto-Start (15 min)

- [ ] Run the scheduler setup script:

```powershell
cd C:\graxia-os\graxia\packages\quant_os
.\scripts\setup_scheduler.ps1 -PythonPath "C:\graxia-env\Scripts\python.exe"
```

- [ ] Verify three tasks created:

```powershell
Get-ScheduledTask -TaskName "QuantOS-MegaCollect","GRAXIA-OS Bot","GRAXIA-OS HealthCheck" | Format-Table TaskName, State
```

- [ ] Manual verification via Task Scheduler GUI:
  - [ ] `QuantOS-MegaCollect`: Daily at 13:00 UTC
  - [ ] `GRAXIA-OS Bot`: At startup, runs `webhook.py --live`
  - [ ] `GRAXIA-OS HealthCheck`: At startup, runs `monitoring/health_check.py`
- [ ] All tasks: "Run whether user is logged on or not" + "Run with highest privileges"
- [ ] Test: `Restart-Computer -Force` → after reboot, verify both GRAXIA-OS tasks are Running:

```powershell
Get-ScheduledTask -TaskName "GRAXIA-OS*" | Get-ScheduledTaskInfo | Format-Table TaskName, LastRunTime, LastTaskResult
```

### Step 7: Standby VPS — Same Steps, Different Config (1h)

Repeat Steps 1-6 on the Hyonix VPS, with these differences:

- [ ] After Step 4, set standby mode:

```powershell
[System.Environment]::SetEnvironmentVariable('STANDBY_MODE','watch_only','Machine')
```

- [ ] Do NOT enable automated trading in MT5 (leave unchecked)
- [ ] Do NOT schedule the MegaCollect task on standby
- [ ] Instead of the main bot task, schedule the standby listener:

```powershell
# Manual: Create task "GRAXIA-OS StandbyListener"
# Action: python -m uvicorn scripts.standby_listener:app --host 0.0.0.0 --port 8000
```

- [ ] Verify `POST /takeover` endpoint is reachable from primary VPS:

```powershell
# From primary VPS:
Invoke-RestMethod -Uri "http://<standby-ip>:8000/takeover" -Method Post -Body '{"action":"activate"}' -ContentType "application/json"
```

- [ ] Test failover via heartbeat deletion on primary:
  - [ ] Delete `C:\graxia-os\graxia\packages\quant_os\data\heartbeat.txt`
  - [ ] Wait 15 min → verify Telegram risk alert: "Bot heartbeat stale — attempting local RESTART"
  - [ ] Wait 30 min → verify Telegram failover alert: "FAILOVER — standby VPS is taking over"
  - [ ] Verify standby switches to active mode

### Step 8: Go Live Readiness (30 min)

- [ ] Primary VPS running 24h with demo account — no crashes, no stale heartbeats
- [ ] Standby VPS verified in cold standby mode — ready to activate on demand
- [ ] Telegram alerts working for all event types: trade_opened, trade_closed, risk_alert, heartbeat, failover_triggered
- [ ] Daily heartbeat received at 00:05 UTC (verify for 7 consecutive days)
- [ ] Heartbeat includes: trades_today, win_rate_7d, balance, P(ruin)
- [ ] Alert level filtering tested: set `ALERT_LEVEL=critical`, verify non-critical suppressed
- [ ] Risk limits validated: max position size, max daily loss, max drawdown configured
- [ ] First LIVE trade parameters locked:
  - [ ] Lot size: 0.01
  - [ ] Stop at: $6.30 max loss
  - [ ] Pre-registration signed in `pre_register_b2.md`
- [ ] Emergency stop procedure documented:
  - [ ] Close all positions: MT5 → Tools → Expert Advisors → disable
  - [ ] Kill bot: Task Scheduler → disable GRAXIA-OS Bot task
  - [ ] Emergency contact: Telegram bot still works for manual commands

---

## Post-Deployment Verification (run weekly)

```powershell
# Check scheduled tasks are healthy
Get-ScheduledTask -TaskName "GRAXIA-OS*" | Get-ScheduledTaskInfo | Format-Table TaskName, LastRunTime, LastTaskResult, NextRunTime

# Check heartbeat file is fresh
Get-ChildItem C:\graxia-os\graxia\packages\quant_os\data\heartbeat.txt | Select-Object LastWriteTime

# Check disk space
Get-PSDrive C | Select-Object Used, Free

# Check MT5 is running
Get-Process -Name "metatrader*" -ErrorAction SilentlyContinue | Format-Table ProcessName, Id, StartTime
```

---

## Related Documents

- `docs/infrastructure_setup.md` — Full infrastructure guide with environment variable reference
- `docs/vps_budget_comparison.md` — Cost comparison across VPS providers
- `scripts/setup_scheduler.ps1` — Automated Task Scheduler registration
- `pre_register_b2.md` — Phase B2 pre-registration (first live trade parameters)
