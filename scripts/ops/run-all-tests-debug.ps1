#!/usr/bin/env pwsh
# Run All Tests + Debug Report
# รัน tests ทั้งหมดและสร้าง debug report

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$reportFile = "test-debug-report-$timestamp.md"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Graxia OS - All Tests + Debug         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$results = @{
    unit = @{ passed = 0; failed = 0; errors = @() }
    integration = @{ passed = 0; failed = 0; errors = @() }
    chaos = @{ passed = 0; failed = 0; errors = @() }
    total = @{ passed = 0; failed = 0 }
}

# 1. Unit Tests
Write-Host "[1/3] Running Unit Tests..." -ForegroundColor Yellow
try {
    $output = python -m pytest tests\unit -v --tb=short 2>&1 | Out-String
    if ($output -match "passed") {
        $results.unit.passed = [int]($output -match "(\d+) passed" | ForEach-Object { $matches[1] })
    }
    if ($output -match "failed") {
        $results.unit.failed = [int]($output -match "(\d+) failed" | ForEach-Object { $matches[1] })
        $results.unit.errors = $output -split "`n" | Where-Object { $_ -match "FAILED|ERROR" }
    }
    Write-Host "  ✓ Unit: $($results.unit.passed) passed, $($results.unit.failed) failed" -ForegroundColor Green
} catch {
    Write-Warning "  Unit tests error: $_"
}

# 2. Integration Tests
Write-Host "[2/3] Running Integration Tests..." -ForegroundColor Yellow
try {
    $output = python -m pytest tests\integration -v --tb=short 2>&1 | Out-String
    if ($output -match "passed") {
        $results.integration.passed = [int]($output -match "(\d+) passed" | ForEach-Object { $matches[1] })
    }
    if ($output -match "failed") {
        $results.integration.failed = [int]($output -match "(\d+) failed" | ForEach-Object { $matches[1] })
        $results.integration.errors = $output -split "`n" | Where-Object { $_ -match "FAILED|ERROR" }
    }
    Write-Host "  ✓ Integration: $($results.integration.passed) passed, $($results.integration.failed) failed" -ForegroundColor Green
} catch {
    Write-Warning "  Integration tests error: $_"
}

# 3. Chaos Tests
Write-Host "[3/3] Running Chaos Tests..." -ForegroundColor Yellow
try {
    $output = python -m pytest tests\brutal\test_chaos_all_100_features.py -v --tb=short 2>&1 | Out-String
    if ($output -match "passed") {
        $results.chaos.passed = [int]($output -match "(\d+) passed" | ForEach-Object { $matches[1] })
    }
    if ($output -match "failed") {
        $results.chaos.failed = [int]($output -match "(\d+) failed" | ForEach-Object { $matches[1] })
        $results.chaos.errors = $output -split "`n" | Where-Object { $_ -match "FAILED|ERROR" }
    }
    Write-Host "  ✓ Chaos: $($results.chaos.passed) passed, $($results.chaos.failed) failed" -ForegroundColor Green
} catch {
    Write-Warning "  Chaos tests error: $_"
}

# Calculate totals
$results.total.passed = $results.unit.passed + $results.integration.passed + $results.chaos.passed
$results.total.failed = $results.unit.failed + $results.integration.failed + $results.chaos.failed
$total = $results.total.passed + $results.total.failed
$percent = if ($total -gt 0) { [math]::Round(($results.total.passed / $total) * 100, 1) } else { 0 }

# Save simple results
$simpleReport = @"
Test Report - $timestamp

Unit: $($results.unit.passed) passed, $($results.unit.failed) failed
Integration: $($results.integration.passed) passed, $($results.integration.failed) failed
Chaos: $($results.chaos.passed) passed, $($results.chaos.failed) failed

Total: $percent% ($($results.total.passed)/$total)

Status: $(if ($results.total.failed -eq 0) { "ALL PASSING" } else { "$($results.total.failed) FAILED" })
"@

$simpleReport | Out-File -FilePath $reportFile -Encoding UTF8

# Display Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Test Results Summary                  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Unit:        $($results.unit.passed) passed, $($results.unit.failed) failed" -ForegroundColor $(if($results.unit.failed -eq 0){"Green"}else{"Yellow"})
Write-Host "Integration: $($results.integration.passed) passed, $($results.integration.failed) failed" -ForegroundColor $(if($results.integration.failed -eq 0){"Green"}else{"Yellow"})
Write-Host "Chaos:       $($results.chaos.passed) passed, $($results.chaos.failed) failed" -ForegroundColor $(if($results.chaos.failed -eq 0){"Green"}else{"Yellow"})
Write-Host ""
Write-Host "Total: $percent% ($($results.total.passed)/$total)" -ForegroundColor $(if($results.total.failed -eq 0){"Green"}else{"Yellow"})
Write-Host ""
Write-Host "📄 Debug Report: $reportFile" -ForegroundColor Cyan
Write-Host ""

if ($results.total.failed -eq 0) {
    Write-Host "🎉 ALL TESTS PASSING! Ready for production!" -ForegroundColor Green
} else {
    Write-Host "⚠️ $($results.total.failed) tests failed. Check $reportFile for details." -ForegroundColor Yellow
}
