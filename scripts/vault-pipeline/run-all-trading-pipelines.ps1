# run-all-trading-pipelines.ps1 — Master orchestrator for all 10 trading pipelines
# Runs all pipelines in sequence, outputs summary

param(
    [switch]$DryRun,
    [switch]$Sample
)

$ErrorActionPreference = "Continue"
$pipelineDir = "C:\Users\menum\graxia os\scripts\vault-pipeline"
$logFile = "$env:USERPROFILE\.graxia\trading-pipelines.log"
$results = @()

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts | $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host "[$ts] $msg" -ForegroundColor Gray
}

function Run-Pipeline([string]$name, [string]$scriptPath, [string[]]$args) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Log "START: $name"
    try {
        $output = & $scriptPath @args 2>&1 | Out-String
        $sw.Stop()
        $status = "OK"
        Write-Log "DONE: $name ($($sw.Elapsed.TotalSeconds.ToString('F1'))s)"
        return @{ Name = $name; Status = $status; Time = $sw.Elapsed.TotalSeconds; Output = $output }
    } catch {
        $sw.Stop()
        Write-Log "FAIL: $name - $($_.Exception.Message)"
        return @{ Name = $name; Status = "FAIL"; Time = $sw.Elapsed.TotalSeconds; Output = $_.Exception.Message }
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  TRADING PIPELINE ORCHESTRATOR" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  DryRun: $DryRun | Sample: $Sample" -ForegroundColor Gray
Write-Host ""

$dryArg = if ($DryRun) { "-DryRun" } else { "" }
$sampleArg = if ($Sample) { "-UseSampleData" } else { "" }

# Pipeline 1: Backtest Sync
$results += Run-Pipeline "1-Backtest Sync" "$pipelineDir\trading-backtest-sync.ps1" @(if($DryRun){"-DryRun"})

# Pipeline 2: ML Model Registry
$results += Run-Pipeline "2-ML Registry" "$pipelineDir\ml-model-registry.ps1" @(if($DryRun){"-DryRun"})

# Pipeline 3: Strategy KB
Write-Log "START: 3-Strategy KB"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" "$pipelineDir\strategy_kb.py" 2>&1 | Out-Null
    $sw.Stop()
    $results += @{ Name = "3-Strategy KB"; Status = "OK"; Time = $sw.Elapsed.TotalSeconds }
} catch {
    $sw.Stop()
    $results += @{ Name = "3-Strategy KB"; Status = "FAIL"; Time = $sw.Elapsed.TotalSeconds }
}

# Pipeline 4: Macro Dashboard
$results += Run-Pipeline "4-Macro Dashboard" "$pipelineDir\macro-dashboard.ps1" @()

# Pipeline 5: Trade Journal
$results += Run-Pipeline "5-Trade Journal" "$pipelineDir\trade-journal.ps1" @(if($Sample){"-UseSampleData"})

# Pipeline 6: Regime Sync
Write-Log "START: 6-Regime Sync"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $regimeArg = if ($Sample) { "--sample" } else { "" }
    & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" "$pipelineDir\regime_sync.py" $regimeArg 2>&1 | Out-Null
    $sw.Stop()
    $results += @{ Name = "6-Regime Sync"; Status = "OK"; Time = $sw.Elapsed.TotalSeconds }
} catch {
    $sw.Stop()
    $results += @{ Name = "6-Regime Sync"; Status = "FAIL"; Time = $sw.Elapsed.TotalSeconds }
}

# Pipeline 7: Risk Dashboard
$results += Run-Pipeline "7-Risk Dashboard" "$pipelineDir\risk-dashboard.ps1" @(if($Sample){"-Sample"})

# Pipeline 8: Attribution
Write-Log "START: 8-Attribution"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" "$pipelineDir\attribution.py" 2>&1 | Out-Null
    $sw.Stop()
    $results += @{ Name = "8-Attribution"; Status = "OK"; Time = $sw.Elapsed.TotalSeconds }
} catch {
    $sw.Stop()
    $results += @{ Name = "8-Attribution"; Status = "FAIL"; Time = $sw.Elapsed.TotalSeconds }
}

# Pipeline 9: Signal Quality
Write-Log "START: 9-Signal Quality"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" "$pipelineDir\signal_quality.py" 2>&1 | Out-Null
    $sw.Stop()
    $results += @{ Name = "9-Signal Quality"; Status = "OK"; Time = $sw.Elapsed.TotalSeconds }
} catch {
    $sw.Stop()
    $results += @{ Name = "9-Signal Quality"; Status = "FAIL"; Time = $sw.Elapsed.TotalSeconds }
}

# Pipeline 10: Ensemble Optimizer
Write-Log "START: 10-Ensemble Optimizer"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" "$pipelineDir\ensemble_optimizer.py" 2>&1 | Out-Null
    $sw.Stop()
    $results += @{ Name = "10-Ensemble Optimizer"; Status = "OK"; Time = $sw.Elapsed.TotalSeconds }
} catch {
    $sw.Stop()
    $results += @{ Name = "10-Ensemble Optimizer"; Status = "FAIL"; Time = $sw.Elapsed.TotalSeconds }
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  RESULTS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$okCount = ($results | Where-Object { $_.Status -eq "OK" }).Count
$failCount = ($results | Where-Object { $_.Status -eq "FAIL" }).Count
$totalTime = ($results | Measure-Object -Property Time -Sum).Sum

foreach ($r in $results) {
    $color = if ($r.Status -eq "OK") { "Green" } else { "Red" }
    $icon = if ($r.Status -eq "OK") { "OK" } else { "FAIL" }
    Write-Host ("  [{0}] {1,-25} {2,6:F1}s" -f $icon, $r.Name, $r.Time) -ForegroundColor $color
}

Write-Host ""
Write-Host "  Total: $($results.Count) | OK: $okCount | FAIL: $failCount | Time: $([math]::Round($totalTime, 1))s" -ForegroundColor $(if($failCount -eq 0){'Green'}else{'Yellow'})
Write-Host ""

Write-Log "COMPLETE: $okCount/$($results.Count) OK, $totalTime total seconds"

# Graph Update: Run graphify to update vault knowledge graph
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  GRAPH UPDATE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
$graphSw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $vaultPath = "C:\Users\menum\Documents\ObsidianVault\Second Brain"
    & graphify update "$vaultPath" 2>&1 | Out-Null
    $graphSw.Stop()
    Write-Log "GRAPHIFY: Updated vault graph ($($graphSw.Elapsed.TotalSeconds.ToString('F1'))s)"
    Write-Host "  [OK] graphify graph updated in $($graphSw.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Green
} catch {
    $graphSw.Stop()
    Write-Log "GRAPHIFY: graph update failed - $($_.Exception.Message)"
    Write-Host "  [FAIL] graphify graph update - $($_.Exception.Message)" -ForegroundColor Red
}
