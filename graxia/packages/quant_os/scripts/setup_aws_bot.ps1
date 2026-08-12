# ═══════════════════════════════════════════════════════════════════════════
# setup_aws_bot.ps1 — AWS Windows t2.micro Setup for MT5 Trading Bot
# Run this on the AWS EC2 Windows instance AFTER RDP connection
# ═══════════════════════════════════════════════════════════════════════════

$VPS_API = "http://27.254.134.59:8751"
$SOURCE_REPO = "https://github.com/your-org/graxia-os.git"  # TODO: set after push

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Graxia Trading Bot — AWS Windows Setup" -ForegroundColor Cyan
Write-Host " VPS API: $VPS_API" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# ── 1. Disable Windows Update Auto-Reboot ─────────────────────────────────
Write-Host "`n[1/9] Disabling Windows Update auto-reboot..." -ForegroundColor Yellow
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoUpdate /t REG_DWORD /d 1 /f 2>$null
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update" /v AUOptions /t REG_DWORD /d 1 /f 2>$null
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f 2>$null
Write-Host "   OK Auto-reboot disabled" -ForegroundColor Green

# ── 2. Disable RDP session timeout ────────────────────────────────────────
Write-Host "[2/9] Disabling RDP session timeout..." -ForegroundColor Yellow
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services" /v MaxIdleTime /t REG_DWORD /d 0 /f 2>$null
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services" /v fResetBroken /t REG_DWORD /d 0 /f 2>$null
Write-Host "   OK Session timeout disabled" -ForegroundColor Green

# ── 3. Create swap file (4GB) — ESSENTIAL for 1GB RAM ─────────────────────
Write-Host "[3/9] Creating 4GB swap file..." -ForegroundColor Yellow
try {
    fsutil file createnew C:\swapfile.sys 4294967296 2>&1 | Out-Null
    wmic computersystem set AutomaticManagedPagefile=False 2>&1 | Out-Null
    wmic pagefileset create name="C:\swapfile.sys" 2>&1 | Out-Null
    wmic pagefileset where name="C:\swapfile.sys" set InitialSize=4096,MaximumSize=4096 2>&1 | Out-Null
    Write-Host "   OK Swap 4GB created" -ForegroundColor Green
} catch {
    Write-Host "   WARN Swap creation failed (will retry after reboot): $_" -ForegroundColor Yellow
}

# ── 4. Install Python 3.12 ────────────────────────────────────────────────
Write-Host "[4/9] Installing Python 3.12..." -ForegroundColor Yellow
$pythonUrl = "https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe"
$pythonInstaller = "$env:TEMP\python-installer.exe"

try {
    Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller -UseBasicParsing
    Start-Process -Wait -FilePath $pythonInstaller -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0"
    Write-Host "   OK Python installed" -ForegroundColor Green
} catch {
    Write-Host "   FAIL Python install failed: $_" -ForegroundColor Red
    exit 1
}

# Refresh PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# ── 5. Install Python packages ────────────────────────────────────────────
Write-Host "[5/9] Installing Python packages..." -ForegroundColor Yellow
pip install MetaTrader5 pandas numpy requests python-dotenv aiohttp httpx 2>&1 | Out-Null
Write-Host "   OK Python packages installed" -ForegroundColor Green

# ── 6. Download Pepperstone MT5 ───────────────────────────────────────────
Write-Host "[6/9] Downloading Pepperstone MT5..." -ForegroundColor Yellow
if (!(Test-Path "C:\MT5")) { New-Item -ItemType Directory -Path "C:\MT5" -Force | Out-Null }
$mt5Installer = "C:\MT5\Pepperstone5setup.exe"
if (!(Test-Path $mt5Installer)) {
    try {
        Invoke-WebRequest -Uri "https://download.mql5.com/cdn/web/pepperstone.ltd/mt5/Pepperstone5setup.exe" `
            -OutFile $mt5Installer -UseBasicParsing
        Write-Host "   OK MT5 installer downloaded" -ForegroundColor Green
    } catch {
        Write-Host "   WARN MT5 download failed — download manually from pepperstone.com" -ForegroundColor Yellow
    }
} else {
    Write-Host "   OK MT5 installer already exists" -ForegroundColor Green
}

# ── 7. Install NSSM (for headless MT5 service) ───────────────────────────
Write-Host "[7/9] Installing NSSM for headless MT5..." -ForegroundColor Yellow
if (!(Test-Path "C:\Windows\System32\nssm.exe")) {
    try {
        Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "$env:TEMP\nssm.zip" -UseBasicParsing
        Expand-Archive -Path "$env:TEMP\nssm.zip" -DestinationPath "$env:TEMP\nssm" -Force
        Copy-Item "$env:TEMP\nssm\nssm-2.24\win64\nssm.exe" "C:\Windows\System32\nssm.exe" -Force
        Write-Host "   OK NSSM installed" -ForegroundColor Green
    } catch {
        Write-Host "   WARN NSSM install failed" -ForegroundColor Yellow
    }
} else {
    Write-Host "   OK NSSM already installed" -ForegroundColor Green
}

# ── 8. Download trading bot source from VPS ──────────────────────────────
Write-Host "[8/9] Downloading bot source from VPS..." -ForegroundColor Yellow
$botDir = "C:\graxia-bot"
if (!(Test-Path $botDir)) {
    try {
        # SSH to VPS and create tar of quant_os source
        $tmpTar = "$env:TEMP\quant_os.tar.gz"
        ssh root@27.254.134.59 "cd /opt/graxia-trading && tar czf /tmp/qos.tar.gz quant_os/" 2>&1 | Out-Null
        scp root@27.254.134.59:/tmp/qos.tar.gz $tmpTar 2>&1 | Out-Null
        # Extract
        New-Item -ItemType Directory -Path $botDir -Force | Out-Null
        tar xzf $tmpTar -C $botDir
        Remove-Item $tmpTar -Force -ErrorAction SilentlyContinue
        Write-Host "   OK Bot source downloaded to $botDir" -ForegroundColor Green
    } catch {
        Write-Host "   WARN Could not download from VPS: $_" -ForegroundColor Yellow
        Write-Host "   You may need to copy files manually to $botDir" -ForegroundColor Yellow
    }
} else {
    Write-Host "   OK Bot source already exists" -ForegroundColor Green
}

# ── 9. Create .env with VPS API endpoint ─────────────────────────────────
Write-Host "[9/9] Creating .env config..." -ForegroundColor Yellow
$envFile = "$botDir\quant_os\.env"
$envContent = @"
# Graxia Trading Bot — AWS Instance Config
VPS_API_URL=$VPS_API
TRADING_MODE=PAPER
SYMBOL=XAUUSD
LOT_SIZE=0.01
B2_STOP_DOLLARS=3.00
MIN_CONFIDENCE=0.75
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
"@
Set-Content -Path $envFile -Value $envContent -Encoding UTF8
Write-Host "   OK .env created at $envFile" -ForegroundColor Green

# ── 10. Set Auto-Logon ──────────────────────────────────────────────────
Write-Host "[10/10] Setting up auto-logon..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri "https://live.sysinternals.com/Autologon.exe" -OutFile "C:\Autologon.exe" -UseBasicParsing
    Write-Host "   OK Autologon downloaded at C:\Autologon.exe" -ForegroundColor Green
    Write-Host "   Run C:\Autologon.exe manually to set auto-login" -ForegroundColor Magenta
} catch {
    Write-Host "   WARN Could not download Autologon" -ForegroundColor Yellow
}

# ── Summary ──────────────────────────────────────────────────────────────
Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host " SETUP COMPLETE" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "`nNEXT STEPS:" -ForegroundColor Yellow
Write-Host "  1. REBOOT now (restart to apply swap + settings)" -ForegroundColor White
Write-Host "  2. Run C:\Autologon.exe — set admin auto-login" -ForegroundColor White
Write-Host "  3. Install MT5: run C:\MT5\Pepperstone5setup.exe" -ForegroundColor White
Write-Host "  4. Login Pepperstone Demo account in MT5" -ForegroundColor White
Write-Host "  5. Enable 'Allow Algo Trading' in MT5 settings" -ForegroundColor White
Write-Host "  6. Test MT5:" -ForegroundColor White
Write-Host "     python -c `"import MetaTrader5 as mt5; mt5.initialize(); print(mt5.account_info())`"" -ForegroundColor Gray
Write-Host "  7. Start bot:" -ForegroundColor White
Write-Host "     cd C:\graxia-bot\quant_os && python scripts/paper_trade_bot.py" -ForegroundColor Gray
Write-Host "  8. Set bot to auto-start via Task Scheduler" -ForegroundColor White
Write-Host "`nVPS API (signal dashboard):" -ForegroundColor Green
Write-Host "  $VPS_API" -ForegroundColor Green
Write-Host "  $VPS_API/docs  (Swagger UI)" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan

$reboot = Read-Host "`nReboot now? (y/n)"
if ($reboot -eq "y") {
    Restart-Computer
}
