# Google Cloud Free Tier — MT5 Trading Bot Setup

## Step 1: Create Windows Instance via Console (5 min)

1. Go to **https://console.cloud.google.com/compute**
2. Click **"CREATE INSTANCE"**
3. Configure:
   - **Name**: `graxia-trading-bot`
   - **Region**: `us-central1` (or closest to you)
   - **Zone**: any (e.g., `us-central1-a`)
   - **Machine type**: `e2-micro` (Free Tier — 1 vCPU, 1GB RAM)
   - **Boot disk**: Change → **Operating system**: Windows Server → **Windows Server 2022 Datacenter**
   - **Firewall**: Allow **HTTP** and **HTTPS** traffic
4. Click **"CREATE"**
5. Wait 2-3 min → click **"Set Windows password"** → note the password
6. Click **"RDP file"** → download → connect

## Step 2: RDP into Windows

1. Open downloaded `.rdp` file
2. Username: the one shown in console (usually your Google email)
3. Password: the one you just set
4. Accept certificate warning

## Step 3: Run Setup Script

Open **PowerShell as Administrator** on the Windows instance:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force

# Download setup script from your local machine or paste it
# The script will:
# 1. Disable Windows Update auto-reboot
# 2. Create 4GB swap (essential for 1GB RAM)
# 3. Install Python 3.12
# 4. Install MT5 Python packages
# 5. Download Pepperstone MT5 installer
# 6. Download bot source from VPS
```

## Step 4: Install MT5

1. Run `C:\MT5\Pepperstone5setup.exe`
2. Follow installer
3. Open MT5 → File → Open an Account → Search "Pepperstone" → Demo
4. Enable Algo Trading: Tools → Options → Expert Advisors → check "Allow Algo Trading"

## Step 5: Test MT5

```powershell
python -c "import MetaTrader5 as mt5; mt5.initialize(); print(mt5.account_info())"
```

## Step 6: Start Bot

```powershell
cd C:\graxia-bot\quant_os
$env:PYTHONIOENCODING='utf-8'
python scripts/paper_trade_bot.py
```

## Architecture

```
┌─ Google Cloud (e2-micro, Free Forever) ────┐
│  Windows Server 2022                         │
│  MT5 Pepperstone Demo                        │
│  paper_trade_bot.py                          │
│  ↕ MT5 Python API (shared memory)            │
└──────────────────────────────────────────────┘

┌─ VPS 27.254.134.59 (existing) ─────────────┐
│  graxia-api → http://27.254.134.59:8751     │
│  graxia-trainer → daily retrain 02:00 UTC   │
│  graxia-db → PostgreSQL 16                   │
└──────────────────────────────────────────────┘
```

## Cost

| Item | Cost |
|------|------|
| Google Cloud e2-micro | **$0/month** (Always Free) |
| VPS (existing) | $0 extra |
| Pepperstone Demo | $0 |
| **Total** | **$0 forever** |

## Firewall Rules (if needed)

If you need to access the instance from outside:
1. Go to VPC Network → Firewall
2. Create rule:
   - Name: `allow-rdp`
   - Direction: Ingress
   - Action: Allow
   - Targets: All instances
   - Source IP ranges: 0.0.0.0/0
   - Protocols/ports: tcp:3389

## Troubleshooting

**MT5 won't initialize:**
```powershell
python -c "import MetaTrader5 as mt5; print(mt5.initialize()); print(mt5.last_error())"
```

**Bot crashes on start:**
- Make sure `data/` folder exists
- Check `.env` file
- Run with verbose output

**Low memory (1GB RAM):**
- Swap file (4GB) should help
- If still issues, close unnecessary Windows services
- Consider using Google Cloud ARM instance (4 CPU, 24GB RAM) with Linux + Wine
