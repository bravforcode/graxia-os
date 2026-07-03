# AWS Free Tier Deployment Guide

## Prerequisites
- Credit card (Free Tier 12 months, no charge if within limits)
- Email address

## Step 1: Create AWS Account (10 min)

1. Go to **https://aws.amazon.com/free/**
2. Click **"Create an AWS Account"**
3. Enter email, password, AWS account name
4. Choose **"Personal"** plan
5. Enter payment info (charged $1 for verification, refunded)
6. Enter phone number for verification
7. Select **"Basic Support - Free"**
8. Verify email → done

## Step 2: Launch Windows Instance (5 min)

1. Login to AWS Console → search **"EC2"** → click **"Launch Instance"**
2. Configure:
   - **Name**: `graxia-trading-bot`
   - **AMI**: `Microsoft Windows Server 2022 Base` (Free Tier eligible)
   - **Instance type**: `t2.micro` (Free Tier)
   - **Key pair**: Create new → download `.pem` file (keep safe!)
   - **Network settings**: Allow traffic from **"Anywhere"** for RDP (port 3389)
   - **Storage**: 30 GB (Free Tier limit)
3. Click **"Launch Instance"**
4. Wait 2-3 min → go to **Instances** → find `graxia-trading-bot`
5. Click **Connect** → **"RDP client"** → download remote desktop file
6. Get password: click **"Get password"** → upload `.pem` file → decrypt

## Step 3: Connect via RDP

1. Open downloaded `.rdp` file
2. Enter decrypted password
3. Accept certificate warning
4. You're in!

## Step 4: Run Setup Script (15 min)

1. Open **PowerShell as Administrator**
2. Run:
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
irm https://raw.githubusercontent.com/...  # or copy-paste the script
```

Or copy `scripts/setup_aws_bot.ps1` to the instance and run:
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\setup_aws_bot.ps1
```

3. Wait for all steps to complete
4. **REBOOT** when prompted

## Step 5: Install MT5 (10 min)

1. After reboot, RDP back in
2. Run `C:\MT5\Pepperstone5setup.exe`
3. Follow installer (default settings)
4. Open MT5 → **File** → **Open an Account**
5. Search **"Pepperstone"** → select **Demo** server
6. Fill in details → get demo account credentials
7. **Enable Algo Trading**: Tools → Options → Expert Advisors → check "Allow Algo Trading"

## Step 6: Test MT5 (2 min)

Open PowerShell:
```powershell
python -c "import MetaTrader5 as mt5; mt5.initialize(); print(mt5.account_info())"
```

Should print account info (balance, server, etc.)

## Step 7: Start Trading Bot

```powershell
cd C:\graxia-bot\quant_os
$env:PYTHONIOENCODING='utf-8'
python scripts/paper_trade_bot.py
```

## Step 8: Set Auto-Start (Optional)

1. Open **Task Scheduler**
2. Create Basic Task:
   - Name: `Graxia Paper Trade Bot`
   - Trigger: "When the computer starts"
   - Action: "Start a program"
   - Program: `python`
   - Arguments: `C:\graxia-bot\quant_os\scripts\paper_trade_bot.py`
   - Start in: `C:\graxia-bot\quant_os`

## Architecture

```
┌─ AWS Windows (t2.micro) ──────────────┐
│  MT5 (Pepperstone Demo)                │
│  paper_trade_bot.py                    │
│  ↕ MT5 Python API (shared memory)      │
└────────────────────────────────────────┘

┌─ VPS 27.254.134.59 ───────────────────┐
│  graxia-api (http://:8751)             │
│  graxia-trainer (daily retrain)        │
│  graxia-db (PostgreSQL)                │
└────────────────────────────────────────┘
```

## Cost

| Item | Cost | Notes |
|------|------|-------|
| AWS t2.micro | $0/month | Free Tier 12 months |
| VPS (existing) | $0 extra | Already paying for it |
| Pepperstone Demo | $0 | Free demo account |
| **Total** | **$0** | |

## Troubleshooting

**MT5 won't initialize:**
```powershell
python -c "import MetaTrader5 as mt5; print(mt5.initialize()); print(mt5.last_error())"
```

**Bot can't connect to MT5:**
- Make sure MT5 is installed and logged in
- Make sure "Allow Algo Trading" is enabled
- Restart MT5

**Bot crashes on start:**
- Check `data/` folder exists
- Check `.env` file has correct settings
- Run with verbose: `python -u scripts/paper_trade_bot.py 2>&1 | Tee-Object -FilePath bot.log`
