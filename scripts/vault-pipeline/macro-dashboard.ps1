<#
.SYNOPSIS
    Pipeline 4: Macro Dashboard → Vault daily sync.

.DESCRIPTION
    Runs macro_to_vault.py to generate a daily macro dashboard note
    in the Obsidian vault. Can be scheduled via Task Scheduler or
    invoked manually.

.PARAMETER Date
    Override date for the dashboard filename (YYYY-MM-DD). Defaults to today.

.PARAMETER DryRun
    Print output path without writing.

.EXAMPLE
    .\macro-dashboard.ps1
    .\macro-dashboard.ps1 -Date "2026-06-25" -DryRun
#>

param(
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "macro_to_vault.py"

if (-not (Test-Path $pythonScript)) {
    Write-Error "Python script not found: $pythonScript"
    exit 1
}

$vaultDir = "C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\macro"
$outFile = Join-Path $vaultDir "$Date.md"

Write-Host "=== Pipeline 4: Macro Dashboard → Vault ===" -ForegroundColor Cyan
Write-Host "  Date:     $Date"
Write-Host "  Output:   $outFile"
Write-Host ""

if ($DryRun) {
    Write-Host "[DryRun] Would write to: $outFile" -ForegroundColor Yellow
    exit 0
}

# Ensure output directory exists
if (-not (Test-Path $vaultDir)) {
    New-Item -ItemType Directory -Path $vaultDir -Force | Out-Null
    Write-Host "  Created:  $vaultDir" -ForegroundColor DarkGray
}

# Run Python script
Write-Host "Running macro_to_vault.py..." -ForegroundColor Green
$env:PYTHONPATH = "C:\Users\menum\graxia os\graxia\packages\quant_os"
& python $pythonScript 2>&1

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Error "Python script failed with exit code $exitCode"
    exit $exitCode
}

if (Test-Path $outFile) {
    $size = (Get-Item $outFile).Length
    Write-Host ""
    Write-Host "[OK] Vault note created: $outFile ($size bytes)" -ForegroundColor Green
} else {
    Write-Error "Output file not created: $outFile"
    exit 1
}
