# regime-alert.ps1 — Real-time regime change alert trigger
# Creates alert note in 00-Inbox\regime-alerts\{timestamp}.md
# Usage: .\regime-alert.ps1 -Regime "TREND_UP" -Confidence 0.78 -Reason "ADX_HIGH"
#        .\regime-alert.ps1 -FromRegime "RANGE" -ToRegime "TREND_UP"

param(
    [string]$Regime = "",
    [string]$FromRegime = "",
    [string]$ToRegime = "",
    [double]$Confidence = 0.0,
    [string]$Reason = "",
    [string]$VaultPath = "C:\Users\menum\Documents\ObsidianVault\Second Brain"
)

$ErrorActionPreference = "Stop"

$alertsDir = Join-Path $VaultPath "00-Inbox\regime-alerts"
if (-not (Test-Path $alertsDir)) {
    New-Item -ItemType Directory -Force -Path $alertsDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$alertFile = Join-Path $alertsDir "$timestamp.md"

# Determine regime display
$displayRegime = if ($ToRegime) { $ToRegime } elseif ($Regime) { $Regime } else { "UNKNOWN" }
$fromDisplay = if ($FromRegime) { $FromRegime } else { "N/A" }

# Regime labels
$regimeLabels = @{
    "TREND_UP"   = "TREND UP"
    "TREND_DOWN" = "TREND DOWN"
    "RANGE"      = "RANGE"
    "UNCLEAR"    = "UNCLEAR"
}
$label = $regimeLabels[$displayRegime]
if (-not $label) { $label = $displayRegime }

# Strategy recommendations per regime
$strategyMap = @{
    "TREND_UP"   = @{ Enable = "ema_crossover, breakout, momentum"; Disable = "mean_reversion, range_scalp"; Sizing = "FULL (100%)" }
    "TREND_DOWN" = @{ Enable = "short_momentum, breakdown"; Disable = "mean_reversion, range_scalp"; Sizing = "MODERATE (80%)" }
    "RANGE"      = @{ Enable = "mean_reversion, range_scalp"; Disable = "breakout, momentum"; Sizing = "REDUCED (60%)" }
    "UNCLEAR"    = @{ Enable = "none"; Disable = "ALL"; Sizing = "MINIMAL (30%)" }
}
$strat = $strategyMap[$displayRegime]
if (-not $strat) { $strat = @{ Enable = "unknown"; Disable = "unknown"; Sizing = "unknown" } }

# Confidence label
$confLabel = if ($Confidence -ge 0.8) { "HIGH" }
             elseif ($Confidence -ge 0.6) { "MEDIUM" }
             else { "LOW" }

# Build markdown
$transitionLine = ""
if ($FromRegime) {
    $fromLabel = $regimeLabels[$FromRegime]
    if (-not $fromLabel) { $fromLabel = $FromRegime }
    $transitionLine = "## Transition`n`n| From | To | Confidence |`n|------|-----|------------|`n| $fromLabel | **$label** | $($Confidence.ToString('P0')) |`n"
}

$reasonLine = ""
if ($Reason) {
    $reasonLine = "`n> **Reason:** ``$Reason```n"
}

$markdown = @"
---
type: regime-alert
regime: $displayRegime
confidence: $Confidence
from_regime: $FromRegime
timestamp: $now
---

# Regime Change Alert

> **New Regime:** $label ($($Confidence.ToString('P0')))
> **Confidence Level:** $confLabel
> **Time:** $now
$reasonLine
---

## Strategy Adjustments

| Action | Strategies |
|--------|-----------|
| **Enable** | $($strat.Enable) |
| **Disable** | $($strat.Disable) |

## Position Sizing

| Level | Recommendation |
|-------|---------------|
| Sizing | **$($strat.Sizing)** |

$transitionLine
---

## Checklist

- [ ] Review affected open positions
- [ ] Adjust position sizing for new regime
- [ ] Check spread state before next entry
- [ ] Update regime in trade journal
- [ ] Verify risk limits for regime
"@

Set-Content -Path $alertFile -Value $markdown -Encoding UTF8
Write-Host "[regime-alert] Alert created: $alertFile" -ForegroundColor Green
Write-Host "  Regime: $label ($($Confidence.ToString('P0')))" -ForegroundColor Cyan
if ($FromRegime) {
    Write-Host "  Transition: $fromLabel -> $label" -ForegroundColor Yellow
}
