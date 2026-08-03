param(
    [string]$PythonPath = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
)

$ErrorActionPreference = "Stop"
$taskName = "QuantOS-MeasurementDaemon"

# Resolve working directory (scripts\.. = project root)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Resolve-Path "$scriptDir\.."
Set-Location $projectRoot

# Action: run the multi-symbol measurement daemon (long-running, 24/7)
$action = New-ScheduledTaskAction -Execute $PythonPath -Argument "scripts/run_measurement_daemon.py" -WorkingDirectory $projectRoot

# Trigger: daily 00:00 (user-level; AtStartup/AtLogOn need admin for this
# principal). The daemon itself runs continuously once started — the daily
# trigger + IgnoreNew keeps one instance alive; re-run this script or
# Start-ScheduledTask after a reboot.
$trigger = New-ScheduledTaskTrigger -Daily -At "00:00"

# Principal: current user, Interactive, Limited
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Settings: never overlap, unlimited execution (long-running daemon).
# NOTE: RestartCount/RestartInterval need admin; without them the daemon is
# restarted by the logon trigger re-firing + manual Start-ScheduledTask.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable:$false

# Register (Force overwrites if task already exists)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force

Write-Host "[OK] Task '$taskName' registered." -ForegroundColor Green
Write-Host "  Trigger: AtStartup | Restart: every 5 min on failure" -ForegroundColor Cyan
Write-Host "  Command: $PythonPath scripts/run_measurement_daemon.py" -ForegroundColor Gray
Write-Host "  Working dir: $projectRoot" -ForegroundColor Gray
