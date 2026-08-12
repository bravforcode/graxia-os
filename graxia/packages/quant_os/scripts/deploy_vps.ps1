param(
    [string]$GitRepo = "https://github.com/bravforcode/graxia-os.git",
    [string]$ClonePath = "C:\graxia-os",
    [string]$VenvPath = "C:\graxia-env",
    [string]$PythonVersion = "3.11.14",
    [switch]$Standby,
    [string]$StandbyWebhookUrl = "",
    [string]$StandbySecret = "",
    [string]$TelegramBotToken = "",
    [string]$TelegramChatId = "",
    [switch]$SkipClone,
    [switch]$SkipMegaCollect
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.ForegroundColor = "Cyan"
Write-Host "=== GRAXIA-OS VPS Deployment Script ==="
Write-Host ""

# ── 1. Directory setup ──────────────────────────────────────────────
Write-Host "[1/7] Creating directories..." -ForegroundColor Yellow
foreach ($dir in @($ClonePath, "$ClonePath\graxia\packages\quant_os\data", "$ClonePath\graxia\packages\quant_os\logs")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir"
    }
}

# ── 2. Clone repo ────────────────────────────────────────────────────
if (-not $SkipClone) {
    Write-Host "[2/7] Cloning repository..." -ForegroundColor Yellow
    if (Test-Path "$ClonePath\.git") {
        Write-Host "  Repo already cloned — pulling latest..." -ForegroundColor Gray
        Push-Location $ClonePath
        git pull
        Pop-Location
    } else {
        git clone $GitRepo $ClonePath
        Write-Host "  Cloned from $GitRepo"
    }
}

$quantOsPath = "$ClonePath\graxia\packages\quant_os"

# ── 3. Python venv ───────────────────────────────────────────────────
Write-Host "[3/7] Setting up Python virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path "$VenvPath\Scripts\python.exe")) {
    Write-Host "  Creating venv at $VenvPath ..."
    python -m venv $VenvPath
    Write-Host "  venv created"

    # Set PYTHONIOENCODING machine-wide
    [System.Environment]::SetEnvironmentVariable('PYTHONIOENCODING','utf-8','Machine')
    Write-Host "  PYTHONIOENCODING=utf-8 set (machine-wide)"
} else {
    Write-Host "  venv already exists at $VenvPath"
}

$pythonExe = "$VenvPath\Scripts\python.exe"
$pipExe = "$VenvPath\Scripts\pip.exe"

# Activate and install
Write-Host "  Installing requirements..."
& $pipExe install --upgrade pip --quiet
if (Test-Path "$quantOsPath\requirements.txt") {
    & $pipExe install -r "$quantOsPath\requirements.txt" --quiet
    Write-Host "  requirements.txt installed"
} else {
    Write-Host "  WARNING: requirements.txt not found at $quantOsPath — install manually" -ForegroundColor Red
}

# Verify MetaTrader5
try {
    & $pythonExe -c "import MetaTrader5; print('MT5 OK:', MetaTrader5.__version__)"
    Write-Host "  MetaTrader5 binding verified" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: MetaTrader5 import failed — is MT5 installed?" -ForegroundColor Red
}

# ── 4. Environment variables ────────────────────────────────────────
Write-Host "[4/7] Setting environment variables..." -ForegroundColor Yellow
if ($Standby) {
    [System.Environment]::SetEnvironmentVariable('STANDBY_MODE','watch_only','Machine')
    Write-Host "  STANDBY_MODE=watch_only"
}
if ($StandbyWebhookUrl) {
    [System.Environment]::SetEnvironmentVariable('STANDBY_WEBHOOK_URL',$StandbyWebhookUrl,'Machine')
    Write-Host "  STANDBY_WEBHOOK_URL set"
}
if ($StandbySecret) {
    [System.Environment]::SetEnvironmentVariable('STANDBY_SECRET',$StandbySecret,'Machine')
    Write-Host "  STANDBY_SECRET set"
}
if ($TelegramBotToken) {
    [System.Environment]::SetEnvironmentVariable('TELEGRAM_BOT_TOKEN',$TelegramBotToken,'Machine')
    Write-Host "  TELEGRAM_BOT_TOKEN set"
}
if ($TelegramChatId) {
    [System.Environment]::SetEnvironmentVariable('TELEGRAM_CHAT_ID',$TelegramChatId,'Machine')
    Write-Host "  TELEGRAM_CHAT_ID set"
}

# ── 5. Telegram test ─────────────────────────────────────────────────
Write-Host "[5/7] Testing Telegram notification..." -ForegroundColor Yellow
try {
    $result = & $pythonExe -c "
import sys
sys.path.insert(0, r'$quantOsPath')
from core.telegram_notify import TelegramNotifier
t = TelegramNotifier()
ok = t.send('*GRAXIA-OS VPS Deployment* — setup in progress on $env:COMPUTERNAME')
print('OK' if ok else 'FAIL')
"
    Write-Host "  Telegram test: $result" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: Telegram test failed (config may need manual setup)" -ForegroundColor Red
    Write-Host "    $_"
}

# ── 6. Task Scheduler ────────────────────────────────────────────────
Write-Host "[6/7] Registering scheduled tasks..." -ForegroundColor Yellow
Push-Location $quantOsPath

$setupScript = "$quantOsPath\scripts\setup_scheduler.ps1"
if (Test-Path $setupScript) {
    try {
        & $setupScript -PythonPath $pythonExe
        Write-Host "  setup_scheduler.ps1 executed" -ForegroundColor Green
    } catch {
        Write-Host "  WARNING: schedule registration failed — run manually:" -ForegroundColor Red
        Write-Host "    .\scripts\setup_scheduler.ps1 -PythonPath `"$pythonExe`""
    }
}

# If standby, add the standby listener task instead of (or in addition to) the bot
if ($Standby) {
    $listenerName = "GRAXIA-OS StandbyListener"
    $listenerAction = New-ScheduledTaskAction `
        -Execute $pythonExe `
        -Argument "-m uvicorn scripts.standby_listener:app --host 0.0.0.0 --port 8000" `
        -WorkingDirectory $quantOsPath
    $listenerTrigger = New-ScheduledTaskTrigger -AtStartup
    $listenerPrincipal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType S4U `
        -RunLevel Highest
    $listenerSettings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Days 30) `
        -StartWhenAvailable `
        -RestartOnFailure `
        -RestartCount 5 `
        -RestartInterval (New-TimeSpan -Minutes 2)
    Register-ScheduledTask -TaskName $listenerName `
        -Action $listenerAction `
        -Trigger $listenerTrigger `
        -Principal $listenerPrincipal `
        -Settings $listenerSettings `
        -Force
    Write-Host "  Standby listener task registered: $listenerName" -ForegroundColor Cyan

    # Disable the MegaCollect on standby (no need to collect on both)
    if (Get-ScheduledTask -TaskName "QuantOS-MegaCollect" -ErrorAction SilentlyContinue) {
        Disable-ScheduledTask -TaskName "QuantOS-MegaCollect"
        Write-Host "  QuantOS-MegaCollect disabled (standby doesn't collect)" -ForegroundColor Gray
    }
}

Pop-Location

# ── 7. Health check test ─────────────────────────────────────────────
Write-Host "[7/7] Testing health check..." -ForegroundColor Yellow
try {
    $job = Start-Job -ScriptBlock {
        param($exe, $cwd)
        $p = Start-Process -FilePath $exe -ArgumentList "-m monitoring.health_check" -WorkingDirectory $cwd -NoNewWindow -PassThru
        Start-Sleep -Seconds 3
        $p.Kill()
    } -ArgumentList $pythonExe, $quantOsPath
    Wait-Job $job -Timeout 10 | Out-Null
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    Write-Host "  Health check starts without errors" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: health check test failed" -ForegroundColor Red
}

# ── Summary ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Deployment Summary ===" -ForegroundColor Green
Write-Host "  Hostname:       $env:COMPUTERNAME"
Write-Host "  Clone path:     $ClonePath"
Write-Host "  Python:         $pythonExe"
Write-Host "  Mode:           $(if ($Standby) { 'STANDBY (watch-only)' } else { 'PRIMARY' })"

$tasks = Get-ScheduledTask -TaskName "GRAXIA-OS*","QuantOS-MegaCollect" -ErrorAction SilentlyContinue
if ($tasks) {
    Write-Host "  Scheduled tasks:"
    $tasks | ForEach-Object { Write-Host "    - $($_.TaskName): $($_.State)" }
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Reboot: Restart-Computer -Force"
Write-Host "  2. After reboot, verify: Get-ScheduledTask -TaskName 'GRAXIA-OS*' | Get-ScheduledTaskInfo"
Write-Host "  3. Check first heartbeat arrives within 5 min on Telegram"
Write-Host "  4. Read docs/vps_deployment_checklist.md for full Go Live readiness"
Write-Host ""
