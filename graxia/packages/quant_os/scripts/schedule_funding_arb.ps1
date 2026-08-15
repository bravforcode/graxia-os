# Register the Trial 4002 funding-arb paper-trade collector as a Windows
# Scheduled Task. Idempotent: re-running replaces the existing task
# (Register-ScheduledTask -Force).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/schedule_funding_arb.ps1
#
# Task: quant_os_funding_arb
#   - runs HOURLY (24x/day) for maximum coverage of Binance's 8h funding
#     interval (00:00 / 08:00 / 16:00 UTC); the collector records funding
#     events strictly after last_checked_at, so even a missed run is caught
#     by the next one (and by -StartWhenAvailable after sleep).
#   - runs as the current user with an interactive token (no stored
#     password), so it only fires while the user is logged on -- acceptable
#     for this paper-only collector on a dev machine.
#   - output appends to reports/paper_trading/funding_arb_run.log
#
# Verify:
#   schtasks /Query /TN quant_os_funding_arb /V /FO LIST
#   schtasks /Run /TN quant_os_funding_arb     # run once immediately

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$taskName = "quant_os_funding_arb"
$batPath = Join-Path $root "scripts\run_funding_arb.bat"

if (-not (Test-Path $batPath)) {
    throw "Missing wrapper script: $batPath"
}

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""
# Omitting -RepetitionDuration => repeat indefinitely (MS XML: no Duration element).
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Write-Output "Registering scheduled task '$taskName' (hourly)..."
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null
Write-Output "SUCCESS: task '$taskName' registered."

Write-Output ""
Write-Output "Next steps:"
Write-Output "  1. Run once immediately:  schtasks /Run /TN $taskName"
Write-Output "  2. Verify:                schtasks /Query /TN $taskName /V /FO LIST"
Write-Output "  3. Health gate:           python scripts/check_funding_arb_health.py"
