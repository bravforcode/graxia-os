param(
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"
$taskName = "QuantOS-MegaCollect"

# Resolve working directory (scripts\.. = project root)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Resolve-Path "$scriptDir\.."
Set-Location $projectRoot

# Compute local time for 13:00 UTC
$utcTrigger = (Get-Date -Year 2000 -Month 1 -Day 1 -Hour 13 -Minute 0 -Second 0 -Kind Utc)
$localTrigger = $utcTrigger.ToLocalTime()
$localTimeStr = $localTrigger.ToString("HH:mm")

# Action: run Python script
$action = New-ScheduledTaskAction -Execute $PythonPath -Argument "scripts/mega_collect.py --skip-ticks --order-count 50 --order-interval 10 --max-spread 0.50 --tick-context" -WorkingDirectory $projectRoot

# Trigger: daily at 13:00 UTC (converted to local)
$trigger = New-ScheduledTaskTrigger -Daily -At $localTimeStr

# Principal: current user, S4U logon (runs when logged off, no password stored)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Highest

# Settings: overlap guard, AC guard, 5-hour cap
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries $false -StopIfGoingOnBatteries $true -MultipleInstancesPolicy StopExisting -ExecutionTimeLimit (New-TimeSpan -Hours 5) -StartWhenAvailable $true

# Register (Force overwrites if task already exists)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force

Write-Host "[OK] Task '$taskName' registered." -ForegroundColor Green
Write-Host "  Runs daily at $localTimeStr local time (13:00 UTC)" -ForegroundColor Cyan
Write-Host "  Command: $PythonPath scripts/mega_collect.py --skip-ticks --order-count 50 --order-interval 10 --max-spread 0.50 --tick-context" -ForegroundColor Gray
Write-Host "  Working dir: $projectRoot" -ForegroundColor Gray
Write-Host "  User: $env:USERDOMAIN\$env:USERNAME (S4U, runs when logged off)" -ForegroundColor Gray
Write-Host "  Max duration: 5 hours | No overlap | AC power required" -ForegroundColor Gray
