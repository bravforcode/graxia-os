# GRAXIA-OS Auto-Start Setup
# Run this as ADMINISTRATOR (right-click → Run as Administrator)
# This sets the bot to start automatically when Windows boots

$botDir = "C:\Users\menum\graxia os\graxia\packages\quant_os"
$scriptPath = "$botDir\scripts\start_bot.bat"
$taskName = "GraxiaOSBot"

Write-Host "=== GRAXIA-OS Auto-Start Setup ===" -ForegroundColor Cyan
Write-Host "Bot dir: $botDir"
Write-Host ""

# 1. Create task scheduler entry
schtasks /CREATE /SC ONSTART /TN $taskName /TR "cmd /c $scriptPath" /RL HIGHEST /F
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Task '$taskName' created" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Task creation failed" -ForegroundColor Red
    Write-Host "  Run PowerShell as Administrator and try again"
}

# 2. Also create a daily heartbeat task
$hbScript = "$botDir\scripts\send_heartbeat.ps1"
@"
`$env:PYTHONIOENCODING='utf-8'
python -c `
  "import sys; sys.path.insert(0,'.'); from core.telegram_notify import TelegramNotifier; TelegramNotifier().heartbeat(0, 0.0, 49940)"
"@ | Out-File -FilePath $hbScript -Encoding utf8

schtasks /CREATE /SC DAILY /TN "GraxiaOSHeartbeat" /TR "powershell -File $hbScript" /ST 00:05 /F
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Daily heartbeat scheduled (00:05 UTC)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Bot is currently RUNNING" -ForegroundColor Green
Write-Host "Logs: $botDir\data\bot_out.log"
Write-Host ""
Write-Host "To stop:  taskkill /f /im python.exe  (or Task Manager)" -ForegroundColor Yellow
Write-Host "To start manually: $scriptPath" -ForegroundColor Yellow
