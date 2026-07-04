# risk-dashboard.ps1 — Pipeline 7: Risk Dashboard → Vault
# Reads quant_os risk system state and writes a vault-compatible risk dashboard.

param(
    [string]$VaultRoot = "C:/Users/menum/Documents/ObsidianVault/Second Brain",
    [string]$QuantRoot = "C:/Users/menum/graxia os/graxia/packages/quant_os",
    [switch]$Sample
)

$ErrorActionPreference = "Continue"

# ── Paths ──────────────────────────────────────────────────────
$RiskLedger   = Join-Path $QuantRoot "data/risk_ledger.json"
$KillSwitch   = Join-Path $QuantRoot "data/kill_switch_state.json"
$TradeLog     = Join-Path $QuantRoot "data/paper_trade_log.csv"
$OutputDir    = Join-Path $VaultRoot "03-resources/trading/risk"
$OutputFile   = Join-Path $OutputDir "dashboard.md"

# ── Risk limits (golden_rules.py) ─────────────────────────────
$MaxDrawdownPct    = 15.0
$MaxDailyLossPct   = 2.0
$MaxWeeklyLossPct  = 5.0
$MaxPositions      = 5
$MaxExposurePct    = 50.0
$CorrelationLimit  = 0.7
$Capital           = 10000.0

# ── Helpers ────────────────────────────────────────────────────
function Read-JsonSafe($Path) {
    if (Test-Path -LiteralPath $Path) {
        try { return Get-Content $Path -Raw | ConvertFrom-Json } catch { return $null }
    }
    return $null
}

function Status-Indicator {
    param([double]$Current, [double]$Limit, [switch]$Invert)
    if ($Limit -le 0) { return "---" }
    $ratio = if ($Invert) { ($Limit - $Current) / $Limit } else { $Current / $Limit }
    if ($ratio -lt 0.5)     { return "[OK]" }
    elseif ($ratio -lt 0.75) { return "[WARN]" }
    else                     { return "[CRIT]" }
}

function Parse-TradeLog {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $lines = Get-Content $Path
    if ($lines.Count -lt 2) { return @() }
    $headers = $lines[0] -split ","
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $trades = @()
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if (-not $lines[$i].Trim()) { continue }
        $parts = $lines[$i] -split ","
        $row = @{}
        for ($j = 0; $j -lt $headers.Count; $j++) {
            if ($j -lt $parts.Count) { $row[$headers[$j].Trim()] = $parts[$j].Trim() }
        }
        if ($row["timestamp"] -and $row["timestamp"].StartsWith($today)) {
            $trades += [PSCustomObject]$row
        }
    }
    return $trades
}

# ── Load data ──────────────────────────────────────────────────
Write-Host "`n  Pipeline 7: Risk Dashboard" -ForegroundColor Cyan
Write-Host "  ==========================" -ForegroundColor Cyan

$ledger    = Read-JsonSafe $RiskLedger
$killState = Read-JsonSafe $KillSwitch
$trades    = Parse-TradeLog $TradeLog

if ($Sample) {
    Write-Host "  Mode: SAMPLE (no live data)" -ForegroundColor Yellow
} else {
    Write-Host "  Ledger: $(if ($ledger) {'loaded'} else {'missing'})" -ForegroundColor Gray
    Write-Host "  KillSwitch: $(if ($killState) {'loaded'} else {'missing'})" -ForegroundColor Gray
    Write-Host "  Trades today: $($trades.Count)" -ForegroundColor Gray
}

# ── Compute metrics ────────────────────────────────────────────
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss UTC")
$today = (Get-Date).ToString("yyyy-MM-dd")

if ($Sample) {
    $drawdown       = 3.2
    $dailyPnl       = -42.50
    $weeklyPnl      = -185.00
    $openPos        = 3
    $grossExp       = 12500.0
    $netExp         = 3200.0
    $longExp        = 7850.0
    $shortExp       = 4650.0
    $symbolExp      = @{XAUUSD=5200; EURUSD=2650; USDJPY=-4650; GBPUSD=2650}
    $cbState        = "CLOSED"
    $cbReason       = ""
    $cbLosses       = 1
    $cbErrorRate    = 0.0
    $ksActive       = $false
    $ksReason       = ""
    $ksActivated    = ""
    $ordersToday    = 4
    $tradesToday    = 2
    $consecLosses   = 1
    $corrPairs      = @(@("XAUUSD","EURUSD",0.62))
} else {
    $drawdown       = [double]($ledger.total_drawdown)
    $weeklyPnl      = [double]($ledger.weekly_realized_loss)
    $openPos        = [int]($ledger.open_positions)
    $grossExp       = [double]($ledger.gross_exposure)
    $symbolExp      = @{}
    if ($ledger.symbol_exposure) {
        foreach ($prop in $ledger.symbol_exposure.PSObject.Properties) {
            $symbolExp[$prop.Name] = [double]$prop.Value
        }
    }
    $longExp = 0; $shortExp = 0
    foreach ($val in $symbolExp.Values) {
        if ($val -ge 0) { $longExp += $val } else { $shortExp += [math]::Abs($val) }
    }
    $netExp = $longExp - $shortExp

    # Daily PnL from trades
    $dailyPnl = 0
    foreach ($t in $trades) {
        $pnlVal = if ($t.pnl_net) { [double]$t.pnl_net } else { 0 }
        $dailyPnl += $pnlVal
    }
    $tradesToday = $trades.Count

    $dailyLossAbs = [double]($ledger.daily_realized_loss)
    $dailyLossPct = if ($Capital -gt 0) { $dailyLossAbs / $Capital * 100 } else { 0 }

    $cbState     = "CLOSED"
    $cbReason    = ""
    $cbLosses    = 0
    $cbErrorRate = 0.0

    $ksActive    = [bool]$killState.active
    $ksReason    = if ($killState.reason) { $killState.reason } else { "" }
    $ksActivated = if ($killState.activated_at_utc) { $killState.activated_at_utc } else { "" }

    $ordersToday  = [int]($ledger.orders_today)
    $tradesToday  = $trades.Count
    $consecLosses = 0
    $corrPairs    = @()
}

$drawdownHeadroom = [math]::Max(0, $MaxDrawdownPct - $drawdown)
$dailyLossUsedPct = if ($Capital -gt 0) { [math]::Round($dailyLossAbs / $Capital * 100, 2) } else { 0 }
$riskBudget = (($drawdown / $MaxDrawdownPct * 100) + $dailyLossUsedPct + ($openPos / $MaxPositions * 100)) / 3

# ── Build markdown ─────────────────────────────────────────────
$ksIndicator = if ($ksActive) { "[ENGAGED]" } else { "[DISENGAGED]" }
$cbIndicator = if ($cbState -eq "CLOSED") { "[OFF]" } else { "[ON $cbState]" }

$symbolRows = ""
foreach ($sym in ($symbolExp.GetEnumerator() | Sort-Object { [math]::Abs($_.Value) } -Descending)) {
    $dir = if ($sym.Value -ge 0) { "LONG" } else { "SHORT" }
    $absVal = [math]::Abs($sym.Value)
    $pct = if ($Capital -gt 0) { $absVal / $Capital * 100 } else { 0 }
    $symbolRows += "| $($sym.Key) | $dir | `$$($absVal.ToString('N2')) | $($pct.ToString('N1'))% |`n"
}
if (-not $symbolRows) { $symbolRows = "| (no positions) | -- | `$0.00 | 0.0% |`n" }

$corrRows = ""
foreach ($pair in $corrPairs) {
    if ($pair.Count -ge 3) {
        $risk = if ($pair[2] -gt $CorrelationLimit) { "HIGH" } else { "OK" }
        $corrRows += "| $($pair[0]) / $($pair[1]) | $($pair[2].ToString('F2')) | $risk |`n"
    }
}
if (-not $corrRows) { $corrRows = "| (no pairs) | -- | -- |`n" }

$budgetFilled = [math]::Floor($riskBudget / 5)
$bar = ("#" * $budgetFilled) + ("." * (20 - $budgetFilled))

$netBias = if ($netExp -gt 0) { "Long" } elseif ($netExp -lt 0) { "Short" } else { "Flat" }

$md = @"
---
type: risk-dashboard
last_updated: $now
drawdown_pct: $drawdown
circuit_breaker: $cbState
kill_switch: $(if ($ksActive) {"ENGAGED"} else {"DISENGAGED"})
source: $(if ($Sample) {"sample"} else {"ledger"})
---

# Risk Dashboard

> Generated: $now | Trade date: $today

## Core Limits

| Metric | Current | Limit | Headroom | Status |
|--------|---------|-------|----------|--------|
| Drawdown | $($drawdown.ToString('F2'))% | $($MaxDrawdownPct)% | $($drawdownHeadroom.ToString('F1'))% | $(Status-Indicator $drawdown $MaxDrawdownPct) |
| Daily P&L | `$$($dailyPnl.ToString('N2')) | $($MaxDailyLossPct)% loss cap | $($dailyLossUsedPct)% used | $(Status-Indicator $dailyLossUsedPct 100) |
| Weekly P&L | `$$($weeklyPnl.ToString('N2')) | $($MaxWeeklyLossPct)% loss cap | -- | -- |
| Open Positions | $openPos | $MaxPositions | $($MaxPositions - $openPos) slots | $(Status-Indicator $openPos $MaxPositions) |

## Circuit Breaker

| Field | Value |
|-------|-------|
| Status | $cbIndicator |
| State | $cbState |
| Reason | $(if ($cbReason) {$cbReason} else {"None"}) |
| Consecutive Losses | $cbLosses |
| Error Rate | $($cbErrorRate.ToString('N1'))% |

## Kill Switch

| Field | Value |
|-------|-------|
| Status | $ksIndicator |
| Reason | $(if ($ksReason) {$ksReason} else {"N/A"}) |
| Activated At | $(if ($ksActivated) {$ksActivated} else {"N/A"}) |

## Exposure

| Metric | Value | Limit |
|--------|-------|-------|
| Gross Exposure | `$$($grossExp.ToString('N2')) | $($MaxExposurePct)% of capital |
| Net Exposure | `$$($netExp.ToString('N2')) | -- |
| Long Exposure | `$$($longExp.ToString('N2')) | -- |
| Short Exposure | `$$($shortExp.ToString('N2')) | -- |

### Exposure by Symbol

| Symbol | Direction | Value | % of Capital |
|--------|-----------|-------|--------------|
$symbolRows
## Direction Summary

- **Net bias:** $netBias (`$$([math]::Abs($netExp).ToString("N2"))`)

## Correlation Risk

| Pair | Correlation | Risk |
|------|-------------|------|
$corrRows
> Threshold: $CorrelationLimit -- Pairs above are correlated.

## Risk Budget

```
$bar $($riskBudget.ToString('N1'))%
```

| Component | Utilization |
|-----------|-------------|
| Drawdown budget | $(if ($MaxDrawdownPct -gt 0) {($drawdown / $MaxDrawdownPct * 100).ToString('N1')} else {"0"})% |
| Daily loss budget | $($dailyLossUsedPct)% |
| Position slots | $(if ($MaxPositions -gt 0) {($openPos / $MaxPositions * 100).ToString('N1')} else {"0"})% |
| **Total budget** | **$($riskBudget.ToString('N1'))%** |

## Trade Activity

| Metric | Value |
|--------|-------|
| Orders Today | $ordersToday |
| Trades Today | $tradesToday |
| Consecutive Losses | $consecLosses |

---
*Auto-generated by risk-dashboard.ps1 -- Pipeline 7: Risk Dashboard to Vault*
"@

# ── Write output ───────────────────────────────────────────────
if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$md | Out-File -FilePath $OutputFile -Encoding utf8 -Force

Write-Host "`n  Dashboard written!" -ForegroundColor Green
Write-Host "  Drawdown: $($drawdown.ToString('F2'))% | CB: $cbState | KS: $(if ($ksActive) {'ENGAGED'} else {'DISENGAGED'})" -ForegroundColor Yellow
Write-Host "  Output: $OutputFile" -ForegroundColor Gray
