# Weekly TSM paper trade wrapper - Friday 22:00 UTC rebalance runner

param(
    [switch]$DryRun,
    [switch]$ForceRebalance,
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Resolve-Path "$scriptDir\.."
$logDir     = Join-Path $projectRoot "artifacts\portfolio\paper_trades\weekly_runs"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd_HH-mm-ss")
$logFile   = Join-Path $logDir "tsm_weekly_${timestamp}.log"

$venvActivate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
    Write-Host "[OK] Virtual environment activated." -ForegroundColor Green
}

$pyScript = Join-Path $scriptDir "tsm_paper_trade.py"
$argsList = @($pyScript)

if ($DryRun) {
    $argsList += "--dry-run"
    Write-Host "[MODE] Dry-run - no MT5 orders will be placed." -ForegroundColor Yellow
} else {
    $argsList += "--live"
    Write-Host "[MODE] Live - connecting to MT5 for order execution." -ForegroundColor Cyan
}

if ($ForceRebalance) {
    $argsList += "--force-rebalance"
    Write-Host "[FLAG] Force rebalance enabled." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "TSM Weekly Rebalance Run" -ForegroundColor Cyan
Write-Host "  UTC Time : $((Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "  Local    : $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "  Mode     : $(if ($DryRun) { 'DRY-RUN' } else { 'LIVE' })"
Write-Host "  Script   : $pyScript"
Write-Host "  Log      : $logFile"
Write-Host ""

$exitCode = 0
try {
    $proc = Start-Process -FilePath $PythonPath -ArgumentList $argsList `
        -WorkingDirectory $projectRoot `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput (Join-Path $logDir "tsm_weekly_${timestamp}_stdout.log") `
        -RedirectStandardError  (Join-Path $logDir "tsm_weekly_${timestamp}_stderr.log")

    $exitCode = $proc.ExitCode

    if ($exitCode -eq 0) {
        Write-Host "[OK] TSM weekly run completed successfully." -ForegroundColor Green
    } else {
        Write-Host "[WARN] TSM weekly run exited with code $exitCode." -ForegroundColor Red
    }
} catch {
    $exitCode = 1
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "Run finished at $((Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')) UTC"
Write-Host "Exit code: $exitCode"
Write-Host "Logs: $logDir"

exit $exitCode
