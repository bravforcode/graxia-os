<#
.SYNOPSIS
    Pipeline 1: Daily Backtest → Vault auto-sync.

.DESCRIPTION
    Reads backtest results from quant_os, generates Obsidian vault notes with
    strategy metrics, and writes them to the trading/backtest vault folder.

    Run daily via Task Scheduler or manually after a backtest suite completes.

.PARAMETER QuantOsRoot
    Root of the quant_os package. Default: ..\graxia\packages\quant_os

.PARAMETER VaultRoot
    Root of the Obsidian vault. Default: ..\Documents\ObsidianVault\Second Brain

.PARAMETER DateOverride
    Override date string (YYYY-MM-DD). Defaults to today.

.PARAMETER DryRun
    Preview what would be written without creating files.

.EXAMPLE
    .\trading-backtest-sync.ps1
    .\trading-backtest-sync.ps1 -DryRun
    .\trading-backtest-sync.ps1 -DateOverride "2026-06-25"
#>

[CmdletBinding()]
param(
    [string]$QuantOsRoot = "C:\Users\menum\graxia os\graxia\packages\quant_os",
    [string]$VaultRoot   = "C:\Users\menum\Documents\ObsidianVault\Second Brain",
    [string]$DateOverride = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# --- Config ---
$VAULT_TRADE_DIR = Join-Path $VaultRoot "03-resources\trading\backtest"
$PYTHON_HELPER   = Join-Path $PSScriptRoot "backtest_to_vault.py"
$RESULTS_DIRS    = @("results", "reports", "artifacts")

# --- Resolve date ---
if ($DateOverride) {
    $Today = $DateOverride
} else {
    $Today = (Get-Date).ToString("yyyy-MM-dd")
}

Write-Host "=== Backtest → Vault Pipeline ===" -ForegroundColor Cyan
Write-Host "Date:       $Today"
Write-Host "QuantOS:    $QuantOsRoot"
Write-Host "Vault:      $VAULT_TRADE_DIR"
Write-Host ""

# --- Find recent backtest JSONs ---
function Find-BacktestFiles {
    param([string]$Root, [string[]]$Subdirs)

    $found = @()
    foreach ($sub in $Subdirs) {
        $dir = Join-Path $Root $sub
        if (-not (Test-Path $dir)) { continue }

        # Match suite files first, then simple results
        $patterns = @(
            "backtest_suite_*.json",
            "backtest_results*.json",
            "backtest_*.json"
        )
        foreach ($pat in $patterns) {
            $files = Get-ChildItem -Path $dir -Filter $pat -File -ErrorAction SilentlyContinue |
                     Sort-Object LastWriteTime -Descending
            foreach ($f in $files) {
                $found += $f
            }
        }
    }
    return $found
}

$backtestFiles = Find-BacktestFiles -Root $QuantOsRoot -Subdirs $RESULTS_DIRS

if ($backtestFiles.Count -eq 0) {
    Write-Host "No backtest JSON files found in:" -ForegroundColor Yellow
    foreach ($sub in $RESULTS_DIRS) {
        $p = Join-Path $QuantOsRoot $sub
        if (Test-Path $p) { Write-Host "  $p" -ForegroundColor DarkGray }
    }
    Write-Host ""
    Write-Host "Creating sample vault note instead..." -ForegroundColor Yellow
    $backtestFiles = @()
}

# --- Process each file ---
$written = @()

if ($backtestFiles.Count -gt 0) {
    Write-Host "Found $($backtestFiles.Count) backtest file(s):" -ForegroundColor Green
    foreach ($f in $backtestFiles) {
        Write-Host "  $($f.Name)  ($($f.LastWriteTime.ToString('yyyy-MM-dd HH:mm')))" -ForegroundColor DarkGray
    }
    Write-Host ""

    # Use the Python helper if available
    if (Test-Path $PYTHON_HELPER) {
        Write-Host "Using Python helper: $PYTHON_HELPER" -ForegroundColor Cyan

        foreach ($f in $backtestFiles) {
            $pyArgs = @(
                $PYTHON_HELPER,
                "--input", $f.FullName,
                "--output-dir", $VAULT_TRADE_DIR
            )

            if (-not $DryRun) {
                $output = & python @pyArgs 2>&1
                foreach ($line in $output) {
                    if ($line -and (Test-Path $line.ToString())) {
                        $written += $line.ToString()
                        Write-Host "  Wrote: $(Split-Path $line -Leaf)" -ForegroundColor Green
                    }
                }
            } else {
                Write-Host "  [DRY RUN] Would run: python $pyArgs" -ForegroundColor Yellow
            }
        }
    } else {
        # Fallback: pure PowerShell parsing
        Write-Host "Python helper not found, using PowerShell fallback" -ForegroundColor Yellow

        foreach ($f in $backtestFiles) {
            $raw = Get-Content $f.FullName -Raw | ConvertFrom-Json
            $dateStr = if ($raw.timestamp) { $raw.timestamp.Substring(0, 10) } else { $Today }

            # Detect suite vs simple
            if ($raw.results) {
                foreach ($sym in $raw.results.PSObject.Properties) {
                    foreach ($strat in $sym.Value.strategies.PSObject.Properties) {
                        $s = $strat.Value
                        $note = Build-VaultNote -Strategy $strat.Name -Symbol $sym.Name `
                            -WinRate $s.win_rate_pct -ProfitFactor $s.profit_factor `
                            -Sharpe $s.sharpe -MaxDD $s.max_drawdown_pct `
                            -ReturnPct $s.total_return_pct -Trades $s.n_trades `
                            -Date $dateStr

                        $outFile = Join-Path $VAULT_TRADE_DIR "${dateStr}_$($sym.Name)_$($strat.Name).md"
                        if (-not $DryRun) {
                            $note | Out-File -FilePath $outFile -Encoding UTF8
                            $written += $outFile
                            Write-Host "  Wrote: $(Split-Path $outFile -Leaf)" -ForegroundColor Green
                        } else {
                            Write-Host "  [DRY RUN] Would write: $outFile" -ForegroundColor Yellow
                        }
                    }
                }
            }
        }
    }
}

# --- Write sample note if no results found ---
if ($written.Count -eq 0 -and -not $DryRun) {
    Write-Host ""
    Write-Host "Writing sample backtest note for format verification..." -ForegroundColor Yellow
    $sampleNote = @"
---
type: backtest
date: $Today
symbol: XAUUSD
strategies: [Momentum]
status: sample
---

# Backtest: Momentum — XAUUSD

**Date:** $Today
**Strategy:** Momentum
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 49.0% |
| Profit Factor | 1.03 |
| Sharpe Ratio | 1.31 |
| Sortino Ratio | 1.82 |
| Max Drawdown | 13.4% |
| Total Return | 69.19% |
| Expectancy | 0.42 |
| Avg R:R | 1.15 |
| CAGR | 24.50% |

## Trade Breakdown

- **Wins / Losses:** 29399 / 30600
- **Long / Short:** 30100 / 29899
- **Avg Win:** $142.30
- **Avg Loss:** -$123.70
- **Max Consecutive Wins:** 14
- **Max Consecutive Losses:** 11
- **Total Fees:** $419993.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]
"@

    $sampleFile = Join-Path $VAULT_TRADE_DIR "${Today}_XAUUSD_Momentum_sample.md"
    $sampleNote | Out-File -FilePath $sampleFile -Encoding UTF8
    $written += $sampleFile
    Write-Host "  Sample: $(Split-Path $sampleFile -Leaf)" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Pipeline complete: $($written.Count) note(s) synced ===" -ForegroundColor Cyan
