# XAUUSD TSM Paper Trade — Weekly Rebalance Runner
# Run every Friday at 22:00 UTC (after NY close)
#
# Setup (Windows Task Scheduler):
#   1. Open Task Scheduler
#   2. Create Basic Task
#   3. Name: "XAUUSD TSM Paper Trade"
#   4. Trigger: Weekly, Every Friday, 22:00 UTC
#   5. Action: Start a Program
#   6. Program: pwsh
#   7. Arguments: -File "C:\Users\menum\graxia os\graxia\packages\quant_os\scripts\run_paper_trade.ps1"
#
# Manual run:
#   pwsh -File "C:\Users\menum\graxia os\graxia\packages\quant_os\scripts\run_paper_trade.ps1"

$ErrorActionPreference = "Stop"

# Paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "tsm_paper_trade_xauusd.py"
$logDir = Join-Path (Split-Path -Parent $scriptDir) "artifacts\paper_trade_xauusd"
$logFile = Join-Path $logDir ("rebalance_{0:yyyy-MM-dd_HH-mm}.log" -f (Get-Date))

# Ensure log directory exists
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Run the paper trade script
Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting XAUUSD TSM Paper Trade..."
Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Script: $pythonScript"
Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Log: $logFile"

try {
    & python $pythonScript --live 2>&1 | Tee-Object -FilePath $logFile
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Completed successfully"
} catch {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $_"
    $_ | Out-File -FilePath $logFile -Append
    exit 1
}
