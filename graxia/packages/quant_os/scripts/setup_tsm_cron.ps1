# TSM Weekly Rebalance - Scheduled Task Setup
# Run as Administrator

param(
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"

$taskName    = "TSM-Weekly-Rebalance"
$taskDesc    = "TSM paper trade weekly rebalance - Friday 22:00 UTC (after NY close)"

$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Resolve-Path "$scriptDir\.."
$wrapperPath = Join-Path $scriptDir "run_tsm_weekly.ps1"

if (-not (Test-Path $wrapperPath)) {
    Write-Host "[ERROR] Wrapper script not found: $wrapperPath" -ForegroundColor Red
    exit 1
}

# Friday 22:00 UTC converted to local time
$utcTrigger  = [DateTime]::new(2000, 1, 1, 22, 0, 0, [DateTimeKind]::Utc)
$localTrigger = $utcTrigger.ToLocalTime()
$localTimeStr = $localTrigger.ToString("HH:mm")

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wrapperPath`"" `
    -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At $localTimeStr

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Write-Host ""
Write-Host "TSM Weekly Rebalance - Scheduled Task Setup" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Task name    : $taskName"
Write-Host "  Schedule     : Every Friday at $localTimeStr local (22:00 UTC)"
Write-Host "  Wrapper      : $wrapperPath"
Write-Host "  Working dir  : $projectRoot"
Write-Host "  User         : $env:USERDOMAIN\$env:USERNAME (S4U)"
Write-Host "  Max duration : 30 minutes"
Write-Host ""

Register-ScheduledTask `
    -TaskName $taskName `
    -Description $taskDesc `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    Write-Host ""
    Write-Host "[OK] Task registered successfully." -ForegroundColor Green
    Write-Host "  Task state   : $($task.State)"
    Write-Host "  Next run     : $($info.NextRunTime)"
    Write-Host ""
    Write-Host "To test:  Start-ScheduledTask -TaskName '$taskName'"
    Write-Host "To remove: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
    Write-Host "To dry-run: powershell -File `"$wrapperPath`" -DryRun"
} else {
    Write-Host "[ERROR] Registration may have failed." -ForegroundColor Red
    exit 1
}
