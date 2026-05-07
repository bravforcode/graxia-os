#!/usr/bin/env pwsh
# Install Graxia OS Auto-Start (Windows Task Scheduler)
# Runs automatically when user logs in

$ErrorActionPreference = "Stop"
$taskName = "GraxiaOS-Daemon"
$root = $PSScriptRoot
$daemonScript = Join-Path $root "scripts\graxia-daemon.ps1"

Write-Host "Installing Graxia OS Auto-Start..." -ForegroundColor Cyan
Write-Host "Task Name: $taskName" -ForegroundColor Gray

# Check if task exists
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Task already exists. Removing old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}

# Create action
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$daemonScript`""

# Create trigger (at logon)
$trigger = New-ScheduledTaskTrigger -AtLogon

# Create settings
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register task
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null

# Start immediately
Start-ScheduledTask -TaskName $taskName

Write-Host "✅ Auto-start installed successfully!" -ForegroundColor Green
Write-Host "" -ForegroundColor Gray
Write-Host "Graxia will start automatically when you log in." -ForegroundColor Gray
Write-Host "Check status: schtasks /query /tn $taskName" -ForegroundColor DarkGray
Write-Host "Manual start: .\scripts\graxia-daemon.ps1" -ForegroundColor DarkGray
Write-Host "Stop daemon:  .\scripts\graxia-daemon.ps1 -Stop" -ForegroundColor DarkGray
