param(
    [string]$PythonPath = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
)

$ErrorActionPreference = "Stop"
$taskName = "QuantOS-FundingArb"

# Resolve working directory (scripts\.. = project root)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Resolve-Path "$scriptDir\.."
Set-Location $projectRoot

# Action: run funding-arb paper trade (check + record real funding events;
# positions already initialized in reports/paper_trading/funding_arb_state.json)
$action = New-ScheduledTaskAction -Execute $PythonPath -Argument "scripts/paper_trade_funding_arb.py" -WorkingDirectory $projectRoot

# Trigger: every 8h (00:00 / 08:00 / 16:00 local), matching the Binance funding interval
$trigger = New-ScheduledTaskTrigger -Daily -At "00:00"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "00:00" -RepetitionInterval (New-TimeSpan -Hours 8) -RepetitionDuration (New-TimeSpan -Days 1)).Repetition

# Principal: current user, Interactive, Limited (same as QuantOS-NewsSentiment)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Settings: no StartWhenAvailable (do not catch up after machine was off),
# IgnoreNew overlap guard, 2h cap (script is a quick fetch, no long pipeline)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable:$false

# Register (Force overwrites if task already exists)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force

Write-Host "[OK] Task '$taskName' registered." -ForegroundColor Green
Write-Host "  Runs every 8h (00:00, 08:00, 16:00 local)" -ForegroundColor Cyan
Write-Host "  Command: $PythonPath scripts/paper_trade_funding_arb.py" -ForegroundColor Gray
Write-Host "  Working dir: $projectRoot" -ForegroundColor Gray
Write-Host "  User: $env:USERNAME (Interactive, Limited) | No StartWhenAvailable | IgnoreNew" -ForegroundColor Gray
