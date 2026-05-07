# Graxia OS - Deployment Validation Script (PowerShell)
# Tests all critical endpoints and services

param(
    [string]$ApiUrl = "https://graxia-api.fly.dev",
    [string]$InternalApiKey = $env:INTERNAL_API_KEY
)

$ErrorActionPreference = "Stop"
$results = @()

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Method = "GET",
        [hashtable]$Headers = @{},
        [string]$Body = $null,
        [int]$ExpectedStatus = 200,
        [int]$TimeoutSec = 30
    )
    
    Write-Host "Testing $Name... " -NoNewline
    
    try {
        $params = @{
            Uri = $Url
            Method = $Method
            Headers = $Headers
            TimeoutSec = $TimeoutSec
            UseBasicParsing = $true
        }
        
        if ($Body) {
            $params.Body = $Body
            $params.ContentType = "application/json"
        }
        
        $response = Invoke-WebRequest @params
        $status = $response.StatusCode
        
        if ($status -eq $ExpectedStatus) {
            Write-Host "✅ PASS (HTTP $status)" -ForegroundColor Green
            return @{ Name = $Name; Status = "PASS"; Code = $status; Error = $null }
        } else {
            Write-Host "❌ FAIL (Expected $ExpectedStatus, got $status)" -ForegroundColor Red
            return @{ Name = $Name; Status = "FAIL"; Code = $status; Error = "Unexpected status" }
        }
    }
    catch {
        Write-Host "❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
        return @{ Name = $Name; Status = "FAIL"; Code = 0; Error = $_.Exception.Message }
    }
}

Write-Host ""
Write-Host "🧪 Graxia OS Deployment Validation" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "API URL: $ApiUrl"
Write-Host ""

# Test 1: Health Check
$results += Test-Endpoint -Name "Health Check" -Url "$ApiUrl/health"

# Test 2: System Health
$results += Test-Endpoint -Name "System Health" -Url "$ApiUrl/api/v1/system/health"

# Test 3: API Info
$results += Test-Endpoint -Name "API Info" -Url "$ApiUrl/api/v1/info"

# Test 4: Documentation (Swagger UI)
$results += Test-Endpoint -Name "API Docs (Swagger)" -Url "$ApiUrl/docs"

# Test 5: Internal endpoints (if key provided)
if ($InternalApiKey) {
    $headers = @{ "Authorization" = "Bearer $InternalApiKey" }
    
    $results += Test-Endpoint `
        -Name "Internal: Run Lead Hunter" `
        -Url "$ApiUrl/api/v1/internal/run-lead-hunter" `
        -Method "POST" `
        -Headers $headers `
        -TimeoutSec 300
}
else {
    Write-Host "⚠️ Skipping internal endpoint tests (no INTERNAL_API_KEY provided)" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "📊 Test Summary" -ForegroundColor Cyan
Write-Host "===============" -ForegroundColor Cyan

$passed = ($results | Where-Object { $_.Status -eq "PASS" }).Count
$failed = ($results | Where-Object { $_.Status -eq "FAIL" }).Count
$total = $results.Count

Write-Host "Total: $total | Passed: $passed | Failed: $failed"
Write-Host ""

if ($failed -eq 0) {
    Write-Host "🎉 All tests passed! Deployment is healthy." -ForegroundColor Green
    exit 0
} else {
    Write-Host "⚠️ $failed test(s) failed. Please check the errors above." -ForegroundColor Red
    
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Check Fly.io logs: flyctl logs --app graxia-api"
    Write-Host "2. Verify secrets are set: flyctl secrets list --app graxia-api"
    Write-Host "3. Check database connection in Supabase dashboard"
    Write-Host "4. Verify Redis connection in Upstash dashboard"
    
    exit 1
}
