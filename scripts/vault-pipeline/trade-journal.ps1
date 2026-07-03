<#
.SYNOPSIS
    Paper Trade Journal to Obsidian Vault pipeline.

.DESCRIPTION
    Reads paper_trade_log.csv, generates daily trade journals
    at Second Brain/07-Daily/trades/{date}.md with summary,
    strategy breakdown, and trade log.

.EXAMPLE
    .\trade-journal.ps1
    .\trade-journal.ps1 -DryRun
#>

param(
    [string]$CsvPath = "C:\Users\menum\graxia os\graxia\packages\quant_os\data\paper_trade_log.csv",
    [string]$VaultDir = "C:\Users\menum\Documents\ObsidianVault\Second Brain\07-Daily\trades",
    [switch]$DryRun,
    [switch]$UseSampleData
)

$ErrorActionPreference = "Stop"

# --- Sample data for testing ---

function New-SampleCsv {
    param([string]$OutPath)

    $sample = @(
        @{ trade_id="T001"; symbol="XAUUSD"; direction="LONG";   entry_time="2026-06-25 08:15:00"; exit_time="2026-06-25 10:30:00"; entry_price="3310.50"; exit_price="3318.75"; qty="0.05"; pnl="41.25";  pnl_pct="0.25"; strategy="trend_following"; regime="trending_up";   notes="morning breakout" }
        @{ trade_id="T002"; symbol="XAUUSD"; direction="SHORT";  entry_time="2026-06-25 13:00:00"; exit_time="2026-06-25 14:45:00"; entry_price="3322.00"; exit_price="3319.50"; qty="0.05"; pnl="12.50";  pnl_pct="0.08"; strategy="mean_reversion"; regime="range_bound"; notes="resistance rejection" }
        @{ trade_id="T003"; symbol="XAUUSD"; direction="LONG";   entry_time="2026-06-25 16:00:00"; exit_time="2026-06-25 17:30:00"; entry_price="3319.00"; exit_price="3315.25"; qty="0.05"; pnl="-18.75"; pnl_pct="-0.12"; strategy="trend_following"; regime="trending_up";  notes="failed breakout" }
        @{ trade_id="T004"; symbol="EURUSD"; direction="LONG";   entry_time="2026-06-26 07:00:00"; exit_time="2026-06-26 09:15:00"; entry_price="1.0845";  exit_price="1.0872";  qty="10000"; pnl="27.00";  pnl_pct="0.25"; strategy="breakout";       regime="trending";    notes="session open" }
        @{ trade_id="T005"; symbol="EURUSD"; direction="SHORT";  entry_time="2026-06-26 11:30:00"; exit_time="2026-06-26 12:00:00"; entry_price="1.0878";  exit_price="1.0885";  qty="10000"; pnl="-7.00";  pnl_pct="-0.06"; strategy="scalp";          regime="range_bound"; notes="stopped out" }
        @{ trade_id="T006"; symbol="XAUUSD"; direction="LONG";   entry_time="2026-06-26 08:30:00"; exit_time="2026-06-26 11:45:00"; entry_price="3305.00"; exit_price="3321.50"; qty="0.05"; pnl="82.50";  pnl_pct="0.50"; strategy="trend_following"; regime="trending_up"; notes="strong momentum" }
        @{ trade_id="T007"; symbol="XAUUSD"; direction="SHORT";  entry_time="2026-06-26 14:00:00"; exit_time="2026-06-26 15:30:00"; entry_price="3325.00"; exit_price="3320.25"; qty="0.05"; pnl="23.75";  pnl_pct="0.15"; strategy="mean_reversion"; regime="range_bound"; notes="reversal" }
        @{ trade_id="T008"; symbol="GBPUSD"; direction="LONG";   entry_time="2026-06-27 08:00:00"; exit_time="2026-06-27 10:00:00"; entry_price="1.2710";  exit_price="1.2735";  qty="8000";  pnl="20.00";  pnl_pct="0.20"; strategy="breakout";       regime="trending";    notes="london session" }
    )

    $header = "trade_id,symbol,direction,entry_time,exit_time,entry_price,exit_price,qty,pnl,pnl_pct,strategy,regime,notes"
    $lines = @($header)
    foreach ($r in $sample) {
        $line = @($r.trade_id, $r.symbol, $r.direction, $r.entry_time, $r.exit_time,
                  $r.entry_price, $r.exit_price, $r.qty, $r.pnl, $r.pnl_pct,
                  $r.strategy, $r.regime, $r.notes) -join ","
        $lines += $line
    }
    [System.IO.File]::WriteAllLines($OutPath, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[ok] sample CSV written to $OutPath" -ForegroundColor Cyan
    return $OutPath
}

# --- Helpers ---

function Get-PnlBadge {
    param([double]$Pnl)
    if ($Pnl -gt 0) {
        return "GREEN +$($Pnl.ToString('F2'))"
    } else {
        return "RED $($Pnl.ToString('F2'))"
    }
}

function ConvertTo-TradeGroups {
    param([array]$Rows)

    $groups = @{}
    foreach ($row in $Rows) {
        $entryStr = $row.entry_time.Trim()
        try { $dt = [datetime]::Parse($entryStr) } catch { continue }
        $key = $dt.ToString("yyyy-MM-dd")

        if (-not $groups.ContainsKey($key)) {
            $groups[$key] = [System.Collections.ArrayList]::new()
        }
        [void]$groups[$key].Add($row)
    }
    return $groups
}

# --- Main pipeline ---

$csvFile = $CsvPath
if ($UseSampleData -or -not (Test-Path $csvFile)) {
    $samplePath = Join-Path (Split-Path $csvFile) "sample_trades.csv"
    $csvFile = New-SampleCsv -OutPath $samplePath
}

if (-not (Test-Path $csvFile)) {
    Write-Error "CSV not found: $csvFile"
    exit 1
}

Write-Host "`n[tick] Reading $csvFile" -ForegroundColor Yellow
$raw = Import-Csv -Path $csvFile

# Detect live-log schema (timestamp instead of entry_time) and normalize
$headers = $raw[0].PSObject.Properties.Name | ForEach-Object { $_.ToLower() }
$isLiveLog = $headers -contains "timestamp" -and $headers -notcontains "entry_time"

if ($isLiveLog) {
    Write-Host "  [schema] live-log format detected, normalizing..." -ForegroundColor Yellow
    foreach ($row in $raw) {
        # Add normalized properties for downstream code
        $row | Add-Member -NotePropertyName "entry_time" -NotePropertyValue $row.timestamp -Force
        $row | Add-Member -NotePropertyName "symbol" -NotePropertyValue $(if ($row.symbol) { $row.symbol } else { "XAUUSD" }) -Force
        $row | Add-Member -NotePropertyName "exit_time" -NotePropertyValue "" -Force
        $row | Add-Member -NotePropertyName "exit_price" -NotePropertyValue $(if ($row.exit_price) { $row.exit_price } else { "0" }) -Force
        $row | Add-Member -NotePropertyName "qty" -NotePropertyValue $(if ($row.qty) { $row.qty } else { "1" }) -Force
        $pnlVal = if ($row.pnl_net) { $row.pnl_net } elseif ($row.pnl_gross) { $row.pnl_gross } else { "0" }
        $row | Add-Member -NotePropertyName "pnl" -NotePropertyValue $pnlVal -Force
        $row | Add-Member -NotePropertyName "pnl_pct" -NotePropertyValue $(if ($row.pnl_pct) { $row.pnl_pct } else { "0" }) -Force
        $row | Add-Member -NotePropertyName "strategy" -NotePropertyValue $(if ($row.strategy) { $row.strategy } else { "" }) -Force
        $row | Add-Member -NotePropertyName "regime" -NotePropertyValue $(if ($row.regime) { $row.regime } else { "" }) -Force
        $row | Add-Member -NotePropertyName "trade_id" -NotePropertyValue "" -Force
    }
}

Write-Host "  -> $($raw.Count) rows" -ForegroundColor Gray

$groups = ConvertTo-TradeGroups -Rows $raw
Write-Host "  -> $($groups.Count) trading day(s)`n" -ForegroundColor Gray

if (-not $DryRun) {
    if (-not (Test-Path $VaultDir)) {
        New-Item -ItemType Directory -Path $VaultDir -Force | Out-Null
    }
}

$generated = 0

foreach ($day in ($groups.Keys | Sort-Object)) {
    $trades = @($groups[$day])
    $count = $trades.Count
    $pnlSum = ($trades | ForEach-Object { [double]$_.pnl } | Measure-Object -Sum).Sum
    $winners = @($trades | Where-Object { [double]$_.pnl -gt 0 })
    $losers  = @($trades | Where-Object { [double]$_.pnl -le 0 })
    $winRate = if ($count -gt 0) { [math]::Round($winners.Count / $count * 100, 1) } else { 0 }

    $best  = $trades | Sort-Object { [double]$_.pnl } -Descending | Select-Object -First 1
    $worst = $trades | Sort-Object { [double]$_.pnl } | Select-Object -First 1

    # Strategy breakdown
    $strats = @{}
    foreach ($t in $trades) {
        $s = if ($t.strategy) { $t.strategy } else { "unknown" }
        if (-not $strats.ContainsKey($s)) {
            $strats[$s] = @{ count = 0; pnl = 0.0; wins = 0 }
        }
        $strats[$s].count++
        $strats[$s].pnl += [double]$t.pnl
        if ([double]$t.pnl -gt 0) { $strats[$s].wins++ }
    }

    # Build markdown lines
    $md = [System.Collections.ArrayList]::new()

    # Frontmatter
    [void]$md.Add("---")
    [void]$md.Add("type: trade-journal")
    [void]$md.Add("date: $day")
    [void]$md.Add("total_trades: $count")
    [void]$md.Add("daily_pnl: $($pnlSum.ToString('F2'))")
    [void]$md.Add("win_rate: ${winRate}%")
    [void]$md.Add("generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    [void]$md.Add("---")
    [void]$md.Add("")

    # Header
    $pnlBadge = Get-PnlBadge $pnlSum
    [void]$md.Add("# Trade Journal - $day")
    [void]$md.Add("")
    [void]$md.Add("> $count trades  |  P&L **$pnlBadge**  |  Win rate **${winRate}%**")
    [void]$md.Add("")

    # Summary table
    $bestBadge = Get-PnlBadge ([double]$best.pnl)
    $worstBadge = Get-PnlBadge ([double]$worst.pnl)
    [void]$md.Add("## Daily Summary")
    [void]$md.Add("")
    [void]$md.Add("| Metric | Value |")
    [void]$md.Add("|--------|-------|")
    [void]$md.Add("| Total trades | $count |")
    [void]$md.Add("| Winners | $($winners.Count) |")
    [void]$md.Add("| Losers | $($losers.Count) |")
    [void]$md.Add("| Daily P&L | $($pnlSum.ToString('+0.00;-0.00')) |")
    [void]$md.Add("| Win rate | ${winRate}% |")
    [void]$md.Add("| Best trade | $($best.symbol) $bestBadge |")
    [void]$md.Add("| Worst trade | $($worst.symbol) $worstBadge |")
    [void]$md.Add("")

    # Strategy breakdown
    if ($strats.Count -gt 0) {
        [void]$md.Add("## Strategy Breakdown")
        [void]$md.Add("")
        [void]$md.Add("| Strategy | Trades | P&L | Win Rate |")
        [void]$md.Add("|----------|--------|-----|----------|")
        foreach ($sname in ($strats.Keys | Sort-Object)) {
            $sd = $strats[$sname]
            $swr = if ($sd.count -gt 0) { [math]::Round($sd.wins / $sd.count * 100) } else { 0 }
            [void]$md.Add("| $sname | $($sd.count) | $($sd.pnl.ToString('+0.00;-0.00')) | ${swr}% |")
        }
        [void]$md.Add("")
    }

    # Trade log
    [void]$md.Add("## Trade Log")
    [void]$md.Add("")
    [void]$md.Add("| # | Symbol | Dir | Entry | Exit | Entry$ | Exit$ | P&L | Strategy |")
    [void]$md.Add("|---|--------|-----|-------|------|--------|-------|-----|----------|")
    $i = 0
    foreach ($t in $trades) {
        $i++
        $entryT = try { ([datetime]$t.entry_time).ToString("HH:mm") } catch { "--" }
        $exitT  = try { ([datetime]$t.exit_time).ToString("HH:mm") } catch { "--" }
        $tBadge = Get-PnlBadge ([double]$t.pnl)
        [void]$md.Add("| $i | $($t.symbol) | $($t.direction) | $entryT | $exitT | $($t.entry_price) | $($t.exit_price) | $tBadge | $($t.strategy) |")
    }
    [void]$md.Add("")

    # Best trade
    $bestEntry = try { ([datetime]$best.entry_time).ToString("yyyy-MM-dd HH:mm") } catch { $best.entry_time }
    $bestExit  = try { ([datetime]$best.exit_time).ToString("HH:mm") } catch { $best.exit_time }
    [void]$md.Add("## Best Trade")
    [void]$md.Add("")
    [void]$md.Add("- **$($best.symbol)** $($best.direction) - P&L: $bestBadge ($($best.pnl_pct)%)")
    [void]$md.Add("- Strategy: $($best.strategy)  |  Regime: $($best.regime)")
    [void]$md.Add("- Entry: $bestEntry @ $($best.entry_price)")
    [void]$md.Add("- Exit: $bestExit @ $($best.exit_price)")
    [void]$md.Add("")

    # Worst trade
    if ($worst -ne $best) {
        $worstEntry = try { ([datetime]$worst.entry_time).ToString("yyyy-MM-dd HH:mm") } catch { $worst.entry_time }
        $worstExit  = try { ([datetime]$worst.exit_time).ToString("HH:mm") } catch { $worst.exit_time }
        $worstBadge2 = Get-PnlBadge ([double]$worst.pnl)
        [void]$md.Add("## Worst Trade")
        [void]$md.Add("")
        [void]$md.Add("- **$($worst.symbol)** $($worst.direction) - P&L: $worstBadge2 ($($worst.pnl_pct)%)")
        [void]$md.Add("- Strategy: $($worst.strategy)  |  Regime: $($worst.regime)")
        [void]$md.Add("- Entry: $worstEntry @ $($worst.entry_price)")
        [void]$md.Add("- Exit: $worstExit @ $($worst.exit_price)")
        [void]$md.Add("")
    }

    # Regime distribution
    $regimes = @{}
    foreach ($t in $trades) {
        $r = if ($t.regime) { $t.regime } else { "unknown" }
        if (-not $regimes.ContainsKey($r)) { $regimes[$r] = 0 }
        $regimes[$r]++
    }
    if ($regimes.Count -gt 0) {
        [void]$md.Add("## Regime Distribution")
        [void]$md.Add("")
        foreach ($rname in ($regimes.Keys | Sort-Object { $regimes[$_] } -Descending)) {
            [void]$md.Add("- **$rname**: $($regimes[$rname]) trades")
        }
        [void]$md.Add("")
    }

    # Output
    $content = $md -join "`n"
    $outFile = Join-Path $VaultDir "$day.md"

    if ($DryRun) {
        Write-Host "=== $day.md (dry run) ===" -ForegroundColor Cyan
        Write-Host $content
        Write-Host ""
    } else {
        [System.IO.File]::WriteAllText($outFile, $content, [System.Text.UTF8Encoding]::new($false))
        $pnlDisp = $pnlSum.ToString('+0.00;-0.00')
        Write-Host "[ok] $day.md - $count trades, P&L $pnlDisp" -ForegroundColor Green
    }
    $generated++
}

Write-Host "`n---" -ForegroundColor DarkGray
if ($DryRun) {
    Write-Host "  Dry run complete - $generated journal(s)" -ForegroundColor Cyan
} else {
    Write-Host "  Done - $generated journal(s) -> $VaultDir" -ForegroundColor Green
}
Write-Host "---`n" -ForegroundColor DarkGray
