<#
.SYNOPSIS
    ML Model Registry → Vault auto-sync pipeline.

.DESCRIPTION
    Scans quant_os/ml/models/ for trained .pkl files, extracts metadata via
    model_to_vault.py, and generates Obsidian vault notes at:
    Second Brain/03-resources/trading/models/{model_name}_{version}.md

    Also generates Index.md with a registry table of all models.

.PARAMETER ModelDir
    Path to trained model .pkl files.
    Default: C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models

.PARAMETER OutputDir
    Path to vault output directory.
    Default: C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\models

.PARAMETER DryRun
    Preview mode — shows what would be generated without writing files.

.PARAMETER PythonPath
    Python executable path.
    Default: python

.EXAMPLE
    .\ml-model-registry.ps1
    .\ml-model-registry.ps1 -DryRun
    .\ml-model-registry.ps1 -ModelDir "D:\custom\models"
#>

[CmdletBinding()]
param(
    [string]$ModelDir = "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models",
    [string]$OutputDir = "C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\models",
    [switch]$DryRun,
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "model_to_vault.py"

# ── Preflight ──────────────────────────────────────────────────────────────────

Write-Host "`n═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ML Model Registry → Vault Pipeline" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════════`n" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $ModelDir)) {
    Write-Host "[ERROR] Model directory not found: $ModelDir" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $pythonScript)) {
    Write-Host "[ERROR] Python script not found: $pythonScript" -ForegroundColor Red
    Write-Host "        Create model_to_vault.py in: $scriptDir" -ForegroundColor Yellow
    exit 1
}

# Verify Python is available
try {
    $pyVersion = & $PythonPath --version 2>&1
    Write-Host "[OK] Python: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found at: $PythonPath" -ForegroundColor Red
    exit 1
}

# Count model files
$modelFiles = Get-ChildItem -Path $ModelDir -Filter "*.pkl" -File
Write-Host "[OK] Found $($modelFiles.Count) model files in: $ModelDir" -ForegroundColor Green
Write-Host "[OK] Output target: $OutputDir" -ForegroundColor Green

if ($DryRun) {
    Write-Host "[MODE] DRY RUN — no files will be written`n" -ForegroundColor Yellow
}

# ── Run Python Pipeline ────────────────────────────────────────────────────────

Write-Host "`nRunning model_to_vault.py..." -ForegroundColor Cyan

$pyArgs = @(
    $pythonScript,
    "--model-dir", $ModelDir,
    "--output-dir", $OutputDir
)

if ($DryRun) {
    $pyArgs += "--dry-run"
}

try {
    & $PythonPath @pyArgs
    $exitCode = $LASTEXITCODE
} catch {
    Write-Host "[ERROR] Python script failed: $_" -ForegroundColor Red
    exit 1
}

if ($exitCode -ne 0) {
    Write-Host "[ERROR] Python script exited with code: $exitCode" -ForegroundColor Red
    exit $exitCode
}

# ── Post-sync: Verify & Summary ───────────────────────────────────────────────

if (-not $DryRun -and (Test-Path -LiteralPath $OutputDir)) {
    $notes = Get-ChildItem -Path $OutputDir -Filter "*.md" -File
    $modelNotes = $notes | Where-Object { $_.Name -ne "Index.md" }
    $indexNote = $notes | Where-Object { $_.Name -eq "Index.md" }

    Write-Host "`n═══════════════════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  Sync Complete" -ForegroundColor Green
    Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  Model notes generated: $($modelNotes.Count)" -ForegroundColor White
    Write-Host "  Index note:            $(if ($indexNote) { 'OK' } else { 'MISSING' })" -ForegroundColor White
    Write-Host "  Output directory:      $OutputDir" -ForegroundColor White

    if ($modelNotes.Count -gt 0) {
        Write-Host "`n  Generated notes:" -ForegroundColor Gray
        foreach ($n in $modelNotes) {
            Write-Host "    - $($n.Name)" -ForegroundColor Gray
        }
    }

    Write-Host "`n  Open in Obsidian: vault://03-resources/trading/models/Index.md" -ForegroundColor DarkCyan
    Write-Host "═══════════════════════════════════════════════════════════════════`n" -ForegroundColor Green
} elseif ($DryRun) {
    Write-Host "`n[DRY RUN] Pipeline completed. No files written.`n" -ForegroundColor Yellow
}
