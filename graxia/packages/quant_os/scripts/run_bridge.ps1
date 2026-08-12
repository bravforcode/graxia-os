<#
.SYNOPSIS
    Graxia Bridge Orchestrator — runs sync + research + upgrade pipeline.

.DESCRIPTION
    Single entry point for all bridge automation. Sets PYTHONIOENCODING=utf-8
    to prevent UnicodeDecodeError on Windows cp1252 terminals.

.PARAMETER Mode
    - data       : mega_download.py --quick --direct (data pull only)
    - sync       : bridge_automated_sync.py (state, backtest, config, graph)
    - research   : bridge_notebooklm.py (vault ↔ NotebookLM full pipeline)
    - upgrade    : run_upgrade_pipeline.py (full continuous upgrade)
    - upgrade-q  : run_upgrade_pipeline.py --quick (skip ML retrain)
    - full       : sync + research (default)
    - all        : sync + upgrade + research (everything)
    - pull-only  : bridge_notebooklm.py --pull-only (research pull only)

.EXAMPLE
    .\scripts\run_bridge.ps1 -Mode sync
    .\scripts\run_bridge.ps1 -Mode upgrade
    .\scripts\run_bridge.ps1 -Mode all
    .\scripts\run_bridge.ps1 -Mode full
#>

param(
    [ValidateSet("data", "sync", "research", "pull-only", "upgrade", "upgrade-q", "full", "all")]
    [string]$Mode = "full"
)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"

$ScriptDir = Split-Path -Parent $PSCommandPath
$QuantOsRoot = Resolve-Path (Join-Path $ScriptDir "..")
$PythonExe = (Get-Command python).Source

function Run-Script($scriptName, $scriptArgs) {
    $scriptPath = Join-Path $ScriptDir $scriptName
    $fullArgs = @($scriptPath) + $scriptArgs
    $argStr = ($scriptArgs -join " ")
    Write-Host "[bridge] >>> python $scriptName $argStr" -ForegroundColor Cyan
    & $PythonExe $fullArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[bridge] WARNING: $scriptName exited with code $LASTEXITCODE" -ForegroundColor Yellow
    }
}

switch ($Mode) {
    "data" {
        Run-Script "mega_download.py" @("--quick", "--direct")
    }
    "sync" {
        Run-Script "bridge_automated_sync.py" @()
    }
    "research" {
        Run-Script "bridge_notebooklm.py" @()
    }
    "pull-only" {
        Run-Script "bridge_notebooklm.py" @("--pull-only")
    }
    "upgrade" {
        Run-Script "run_upgrade_pipeline.py" @()
    }
    "upgrade-q" {
        Run-Script "run_upgrade_pipeline.py" @("--quick")
    }
    "full" {
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host " Graxia Bridge - Full Automation Run" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        Run-Script "bridge_automated_sync.py" @()
        Write-Host ""
        Run-Script "bridge_notebooklm.py" @()
        Write-Host ""
        Write-Host "[bridge] Full automation run complete." -ForegroundColor Green
    }
    "all" {
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host " Graxia Bridge - COMPLETE (sync + upgrade + research)" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        Run-Script "bridge_automated_sync.py" @()
        Write-Host ""
        Run-Script "run_upgrade_pipeline.py" @()
        Write-Host ""
        Run-Script "bridge_notebooklm.py" @()
        Write-Host ""
        Write-Host "[bridge] Complete automation run finished." -ForegroundColor Green
    }
}
