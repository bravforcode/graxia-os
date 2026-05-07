#Requires -Version 7.0
<#
.SYNOPSIS
    Graxia OS - Production Testing Script (REAL DATA)

.DESCRIPTION
    ทดสอบระบบทั้งหมดด้วยข้อมูลจริง (NO FAKE DATA)
    ต้องมี API deployed และ INTERNAL_API_KEY ก่อนรัน

.PARAMETER ApiUrl
    URL ของ API (default: https://graxia-api.fly.dev)

.PARAMETER InternalApiKey
    INTERNAL_API_KEY สำหรับ authenticate internal endpoints

.PARAMETER FrontendUrl
    URL ของ Frontend (optional, สำหรับ integration tests)

.PARAMETER SkipDestructive
    ข้าม tests ที่มีผลกระทบต่อ database (lead hunter)

.PARAMETER OutputFile
    ไฟล์สำหรับบันทึกผลลัพธ์ (default: test-results-{timestamp}.md)

.EXAMPLE
    .\run-production-tests.ps1 -InternalApiKey "your-key-here"

.EXAMPLE
    $env:INTERNAL_API_KEY = "your-key"
    .\run-production-tests.ps1 -SkipDestructive
#>

param(
    [string]$ApiUrl = "https://graxia-api.fly.dev",
    [string]$InternalApiKey = $env:INTERNAL_API_KEY,
    [string]$FrontendUrl = "",
    [switch]$SkipDestructive,
    [string]$OutputFile = ""
)

# ============================================
# CONFIGURATION
# ============================================
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-not $OutputFile) {
    $timestamp = Get-Date -Format "yyyy-MM-dd-HHmm"
    $OutputFile = "test-results-$timestamp.md"
}

$results = @{
    Phase1 = @{ Name = "Infrastructure"; Tests = @(); Passed = 0; Failed = 0 }
    Phase2 = @{ Name = "API Endpoints"; Tests = @(); Passed = 0; Failed = 0 }
    Phase3 = @{ Name = "Functional"; Tests = @(); Passed = 0; Failed = 0 }
    Phase4 = @{ Name = "Integration"; Tests = @(); Passed = 0; Failed = 0 }
    Phase5 = @{ Name = "Performance"; Tests = @(); Passed = 0; Failed = 0 }
    Phase6 = @{ Name = "Security"; Tests = @(); Passed = 0; Failed = 0 }
}

$allLogs = @()

# ============================================
# HELPER FUNCTIONS
# ============================================

function Write-TestHeader {
    param([string]$Phase, [string]$Title)
    $msg = "`n╔════════════════════════════════════════════════════════════╗`n║ $Phase`: $Title`n╚════════════════════════════════════════════════════════════╝"
    Write-Host $msg -ForegroundColor Cyan
    $script:allLogs += $msg
}

function Write-TestResult {
    param(
        [string]$TestName,
        [bool]$Passed,
        [string]$Details = "",
        [string]$Phase = "Phase1"
    )

    $status = if ($Passed) { "✅ PASS" } else { "❌ FAIL" }
    $color = if ($Passed) { "Green" } else { "Red" }
    $msg = "  [$TestName] $status"
    if ($Details) { $msg += "`n       $Details" }

    Write-Host $msg -ForegroundColor $color
    $script:allLogs += $msg

    # Update counters
    if ($Passed) { $results[$Phase].Passed++ } else { $results[$Phase].Failed++ }
    $results[$Phase].Tests += @{
        Name = $TestName
        Passed = $Passed
        Details = $Details
    }
}

function Invoke-ApiRequest {
    param(
        [string]$Method = "GET",
        [string]$Uri,
        [hashtable]$Headers = @{},
        [string]$Body = "",
        [int]$TimeoutSec = 30,
        [switch]$SkipError
    )

    try {
        $params = @{
            Uri = $Uri
            Method = $Method
            Headers = $Headers
            UseBasicParsing = $true
            TimeoutSec = $TimeoutSec
        }
        if ($Body) {
            $params.Body = $Body
            $params.ContentType = "application/json"
        }

        $response = Invoke-WebRequest @params
        return @{ Success = $true; StatusCode = $response.StatusCode; Content = $response.Content }
    } catch {
        if ($SkipError) {
            return @{ Success = $false; StatusCode = $_.Exception.Response.StatusCode; Error = $_.Exception.Message }
        }
        throw
    }
}

function Test-Connection {
    param([string]$Url, [string]$Name = "Connection")
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

# ============================================
# PHASE 1: INFRASTRUCTURE TESTS
# ============================================

Write-TestHeader "PHASE 1" "Infrastructure Testing"

# Test 1.1: Basic connectivity
Write-Host "`n[1.1] Testing basic connectivity to $ApiUrl..." -ForegroundColor Yellow
$connected = Test-Connection -Url "$ApiUrl/health"
Write-TestResult -TestName "Basic Connectivity" -Passed $connected -Phase "Phase1"

# Test 1.2: Health endpoint returns data
if ($connected) {
    $response = Invoke-ApiRequest -Uri "$ApiUrl/health" -SkipError
    $hasData = $response.Success -and ($response.Content | ConvertFrom-Json).status
    Write-TestResult -TestName "Health Endpoint Data" -Passed $hasData -Phase "Phase1" `
        -Details "Status: $(($response.Content | ConvertFrom-Json).status)"
}

# Test 1.3: Internal API Key check
if (-not $InternalApiKey) {
    Write-Host "`n⚠️  WARNING: INTERNAL_API_KEY not provided. Skipping authenticated tests." -ForegroundColor Yellow
    Write-Host "    Set it with: `$env:INTERNAL_API_KEY = 'your-key'" -ForegroundColor Yellow
} else {
    # Test 1.4: Internal health with auth
    $response = Invoke-ApiRequest -Uri "$ApiUrl/api/v1/internal/health" `
        -Headers @{ "Authorization" = "Bearer $InternalApiKey" } -SkipError

    if ($response.Success) {
        $data = $response.Content | ConvertFrom-Json
        $dbHealthy = $data.services.database -eq "healthy"
        $redisHealthy = $data.services.redis -eq "healthy"

        Write-TestResult -TestName "Database Connection" -Passed $dbHealthy -Phase "Phase1" `
            -Details "Status: $($data.services.database)"
        Write-TestResult -TestName "Redis Connection" -Passed $redisHealthy -Phase "Phase1" `
            -Details "Status: $($data.services.redis)"
    } else {
        Write-TestResult -TestName "Internal Health Auth" -Passed $false -Phase "Phase1" `
            -Details "HTTP $($response.StatusCode)"
    }
}

# ============================================
# PHASE 2: API ENDPOINTS
# ============================================

Write-TestHeader "PHASE 2" "API Endpoint Testing"

# Test 2.1: Public endpoints
$publicEndpoints = @(
    @{ Name = "Health"; Url = "/health" },
    @{ Name = "System Stats"; Url = "/api/v1/system/stats" }
)

foreach ($endpoint in $publicEndpoints) {
    $response = Invoke-ApiRequest -Uri "$ApiUrl$($endpoint.Url)" -SkipError
    Write-TestResult -TestName "Public: $($endpoint.Name)" -Passed $response.Success -Phase "Phase2" `
        -Details "HTTP $($response.StatusCode)"
}

# Test 2.2: Internal endpoints (if key provided)
if ($InternalApiKey) {
    # Should succeed with key
    $response = Invoke-ApiRequest -Uri "$ApiUrl/api/v1/internal/health" `
        -Headers @{ "Authorization" = "Bearer $InternalApiKey" } -SkipError
    Write-TestResult -TestName "Internal: Health (with auth)" -Passed $response.Success -Phase "Phase2" `
        -Details "HTTP $($response.StatusCode)"

    # Should fail without key
    $response = Invoke-ApiRequest -Uri "$ApiUrl/api/v1/internal/health" -SkipError
    $correctlyRejected = -not $response.Success -and $response.StatusCode -eq 401
    Write-TestResult -TestName "Internal: Health (no auth = 401)" -Passed $correctlyRejected -Phase "Phase2" `
        -Details "HTTP $($response.StatusCode)"

    # Queue status
    $response = Invoke-ApiRequest -Uri "$ApiUrl/api/v1/internal/queue-status" `
        -Headers @{ "Authorization" = "Bearer $InternalApiKey" } -SkipError
    if ($response.Success) {
        $queueData = ($response.Content | ConvertFrom-Json).queues
        Write-TestResult -TestName "Internal: Queue Status" -Passed $true -Phase "Phase2" `
            -Details "Queues: $($queueData.Count)"
    } else {
        Write-TestResult -TestName "Internal: Queue Status" -Passed $false -Phase "Phase2" `
            -Details "HTTP $($response.StatusCode)"
    }
}

# ============================================
# PHASE 3: FUNCTIONAL TESTS
# ============================================

Write-TestHeader "PHASE 3" "Functional Testing (REAL DATA)"

if ($InternalApiKey -and -not $SkipDestructive) {
    # Test 3.1: Daily Report (Non-destructive)
    Write-Host "`n[3.1] Generating daily report (real data from database)..." -ForegroundColor Yellow
    $response = Invoke-ApiRequest -Method POST -Uri "$ApiUrl/api/v1/internal/daily-report" `
        -Headers @{ "Authorization" = "Bearer $InternalApiKey" } `
        -TimeoutSec 60 -SkipError

    if ($response.Success) {
        $data = $response.Content | ConvertFrom-Json
        $hasReport = $data.report -and $data.report.date
        Write-TestResult -TestName "Daily Report Generation" -Passed $hasReport -Phase "Phase3" `
            -Details "Date: $($data.report.date), Leads: $($data.report.leads_found), Opp: $($data.report.opportunities_created)"
    } else {
        Write-TestResult -TestName "Daily Report Generation" -Passed $false -Phase "Phase3" `
            -Details "HTTP $($response.StatusCode)"
    }

    # Test 3.2: Cleanup Analysis (Non-destructive - analysis only)
    Write-Host "`n[3.2] Running cleanup analysis (read-only)..." -ForegroundColor Yellow
    $response = Invoke-ApiRequest -Method POST `
        -Uri "$ApiUrl/api/v1/internal/cleanup?days_to_keep=30" `
        -Headers @{ "Authorization" = "Bearer $InternalApiKey" } `
        -TimeoutSec 60 -SkipError

    if ($response.Success) {
        $data = $response.Content | ConvertFrom-Json
        Write-TestResult -TestName "Cleanup Analysis" -Passed $true -Phase "Phase3" `
            -Details "To clean: $($data.cleanup.audit_logs_to_clean) records"
    } else {
        Write-TestResult -TestName "Cleanup Analysis" -Passed $false -Phase "Phase3"
    }

    # Test 3.3: Lead Hunter (Destructive - modifies database)
    Write-Host "`n[3.3] Lead Hunter Test (MODIFIES DATABASE)" -ForegroundColor Red
    Write-Host "       This will ACTUALLY run lead hunter and save leads to database!" -ForegroundColor Red
    $confirm = Read-Host "       Continue? (y/n)"

    if ($confirm -eq 'y') {
        # Get initial stats
        $initialStats = Invoke-ApiRequest -Uri "$ApiUrl/api/v1/system/stats" -SkipError
        $initialLeads = if ($initialStats.Success) { ($initialStats.Content | ConvertFrom-Json).leads_scanned } else { 0 }

        # Run lead hunter
        $start = Get-Date
        $response = Invoke-ApiRequest -Method POST `
            -Uri "$ApiUrl/api/v1/internal/run-lead-hunter" `
            -Headers @{ "Authorization" = "Bearer $InternalApiKey" } `
            -TimeoutSec 300 -SkipError
        $duration = (Get-Date) - $start

        if ($response.Success) {
            $data = $response.Content | ConvertFrom-Json

            # Verify with new stats
            Start-Sleep -Seconds 3  # Wait for DB commit
            $finalStats = Invoke-ApiRequest -Uri "$ApiUrl/api/v1/system/stats" -SkipError
            $finalLeads = if ($finalStats.Success) { ($finalStats.Content | ConvertFrom-Json).leads_scanned } else { 0 }

            $leadsChanged = $finalLeads - $initialLeads
            $details = "Found: $($data.leads_found), DB change: $leadsChanged, Time: $([math]::Round($duration.TotalSeconds, 1))s"

            Write-TestResult -TestName "Lead Hunter Execution" -Passed ($data.leads_found -ge 0) -Phase "Phase3" -Details $details
            Write-TestResult -TestName "Lead Hunter DB Verification" -Passed ($leadsChanged -eq $data.leads_found) -Phase "Phase3" `
                -Details "Consistency: $leadsChanged new in DB"
        } else {
            Write-TestResult -TestName "Lead Hunter Execution" -Passed $false -Phase "Phase3" `
                -Details "HTTP $($response.StatusCode)"
        }
    } else {
        Write-Host "       Skipped." -ForegroundColor Yellow
        $results.Phase3.Tests += @{ Name = "Lead Hunter"; Passed = $null; Details = "Skipped by user" }
    }
} else {
    Write-Host "`n⚠️  Skipping functional tests (no API key or SkipDestructive set)" -ForegroundColor Yellow
}

# ============================================
# PHASE 4: INTEGRATION TESTS
# ============================================

Write-TestHeader "PHASE 4" "Integration Testing"

if ($FrontendUrl) {
    # Test 4.1: Frontend → Backend proxy
    $response = Invoke-ApiRequest -Uri "$FrontendUrl/api/v1/system/health" -SkipError
    Write-TestResult -TestName "Frontend→Backend Proxy" -Passed $response.Success -Phase "Phase4" `
        -Details "HTTP $($response.StatusCode)"

    # Test 4.2: CORS
    $headers = @{ "Origin" = $FrontendUrl }
    $response = Invoke-ApiRequest -Method OPTIONS -Uri "$ApiUrl/health" -Headers $headers -SkipError
    $corsOk = $response.Success -and $response.StatusCode -eq 200
    Write-TestResult -TestName "CORS Headers" -Passed $corsOk -Phase "Phase4"
} else {
    Write-Host "`n⚠️  Frontend URL not provided. Skipping integration tests." -ForegroundColor Yellow
    Write-Host "    Run with: -FrontendUrl 'https://your-app.vercel.app'" -ForegroundColor Yellow
}

# ============================================
# PHASE 5: PERFORMANCE TESTS
# ============================================

Write-TestHeader "PHASE 5" "Performance Testing"

# Test 5.1: Response times
Write-Host "`n[5.1] Measuring response times..." -ForegroundColor Yellow
$endpoints = @(
    @{ Name = "/health"; Url = "/health"; ExpectedMs = 500 }
)

foreach ($ep in $endpoints) {
    $times = @()
    for ($i = 0; $i -lt 5; $i++) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $response = Invoke-ApiRequest -Uri "$ApiUrl$($ep.Url)" -SkipError
        $sw.Stop()
        if ($response.Success) {
            $times += $sw.ElapsedMilliseconds
        }
    }

    if ($times.Count -gt 0) {
        $avg = [math]::Round(($times | Measure-Object -Average).Average, 1)
        $max = ($times | Measure-Object -Maximum).Maximum
        $passed = $avg -lt $ep.ExpectedMs
        Write-TestResult -TestName "Response: $($ep.Name)" -Passed $passed -Phase "Phase5" `
            -Details "Avg: ${avg}ms, Max: ${max}ms (limit: $($ep.ExpectedMs)ms)"
    } else {
        Write-TestResult -TestName "Response: $($ep.Name)" -Passed $false -Phase "Phase5"
    }
}

# Test 5.2: Concurrent requests
Write-Host "`n[5.2] Concurrent request test (10 parallel)..." -ForegroundColor Yellow
$jobs = @()
for ($i = 0; $i -lt 10; $i++) {
    $jobs += Start-Job -ScriptBlock {
        param($url)
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
            return @{ Success = $response.StatusCode -eq 200 }
        } catch { return @{ Success = $false } }
    } -ArgumentList "$ApiUrl/health"
}

$jobs | Wait-Job -Timeout 60 | Out-Null
$results5 = $jobs | Receive-Job
$jobs | Remove-Job

$successCount = ($results5 | Where-Object { $_.Success }).Count
$passed = $successCount -eq 10
Write-TestResult -TestName "Concurrent Requests (10x)" -Passed $passed -Phase "Phase5" `
    -Details "$successCount/10 succeeded"

# ============================================
# PHASE 6: SECURITY TESTS
# ============================================

Write-TestHeader "PHASE 6" "Security Testing"

if ($InternalApiKey) {
    # Test 6.1: Invalid key
    $response = Invoke-ApiRequest -Uri "$ApiUrl/api/v1/internal/health" `
        -Headers @{ "Authorization" = "Bearer invalid_key_12345" } -SkipError
    $rejected = -not $response.Success -and $response.StatusCode -eq 401
    Write-TestResult -TestName "Invalid API Key Rejected" -Passed $rejected -Phase "Phase6" `
        -Details "HTTP $($response.StatusCode)"

    # Test 6.2: Missing auth
    $response = Invoke-ApiRequest -Uri "$ApiUrl/api/v1/internal/health" -SkipError
    $rejected = -not $response.Success -and ($response.StatusCode -eq 401 -or $response.StatusCode -eq 403)
    Write-TestResult -TestName "Missing Auth Rejected" -Passed $rejected -Phase "Phase6" `
        -Details "HTTP $($response.StatusCode)"
}

# ============================================
# SUMMARY
# ============================================

Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                    TEST SUMMARY                            ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

$totalTests = 0
$totalPassed = 0
$totalFailed = 0

foreach ($phase in $results.Keys | Sort-Object) {
    $p = $results[$phase]
    $totalTests += $p.Tests.Count
    $totalPassed += $p.Passed
    $totalFailed += $p.Failed

    $color = if ($p.Failed -eq 0) { "Green" } elseif ($p.Failed -lt $p.Tests.Count / 2) { "Yellow" } else { "Red" }
    Write-Host "`n$($p.Name):" -ForegroundColor $color
    Write-Host "  Tests: $($p.Tests.Count) | Passed: $($p.Passed) | Failed: $($p.Failed)" -ForegroundColor Gray

    if ($p.Failed -gt 0) {
        Write-Host "  Failed tests:" -ForegroundColor Red
        $p.Tests | Where-Object { -not $_.Passed } | ForEach-Object {
            Write-Host "    - $($_.Name): $($_.Details)" -ForegroundColor Red
        }
    }
}

$successRate = if ($totalTests -gt 0) { [math]::Round(($totalPassed / $totalTests) * 100, 1) } else { 0 }

Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor $(if ($totalFailed -eq 0) { "Green" } else { "Red" })
Write-Host "║  TOTAL: $totalTests tests | $totalPassed passed | $totalFailed failed | $successRate% success ║" -ForegroundColor $(if ($totalFailed -eq 0) { "Green" } else { "Red" })
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor $(if ($totalFailed -eq 0) { "Green" } else { "Red" })

# ============================================
# SAVE RESULTS
# ============================================

$mdContent = @"
# Graxia OS Production Test Results

**Date**: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
**API URL**: $ApiUrl
**Frontend URL**: $(if ($FrontendUrl) { $FrontendUrl } else { "N/A" })
**Tester**: $($env:USERNAME)

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | $totalTests |
| Passed | $totalPassed |
| Failed | $totalFailed |
| Success Rate | $successRate% |

## Phase Results

"@

foreach ($phase in $results.Keys | Sort-Object) {
    $p = $results[$phase]
    $status = if ($p.Failed -eq 0) { "✅ PASS" } else { "⚠️  PARTIAL" }
    $mdContent += "`n### $($p.Name): $status`n`n"
    $mdContent += "| Test | Status | Details |`n"
    $mdContent += "|------|--------|---------|`n"

    foreach ($test in $p.Tests) {
        $status = if ($null -eq $test.Passed) { "⏭️ SKIPPED" } elseif ($test.Passed) { "✅ PASS" } else { "❌ FAIL" }
        $details = if ($test.Details) { $test.Details } else { "-" }
        $mdContent += "| $($test.Name) | $status | $details |`n"
    }
}

$mdContent += @"

## Production Readiness

$(if ($totalFailed -eq 0) { "✅ **ALL TESTS PASSED** - System is ready for production!" } else { "⚠️ **TESTS FAILED** - Please fix issues before production deployment." })

## Sign-off

- [ ] All critical tests passed
- [ ] No security vulnerabilities found
- [ ] Performance acceptable (< 500ms average)
- [ ] Real data verified (not fake/test data)

**Approved for Production**: $(if ($totalFailed -eq 0) { "YES" } else { "NO" })

---
Generated by Graxia OS Production Testing Script
"@

$mdContent | Out-File -FilePath $OutputFile -Encoding UTF8
Write-Host "`n📄 Results saved to: $OutputFile" -ForegroundColor Green

# Exit code
exit $totalFailed
