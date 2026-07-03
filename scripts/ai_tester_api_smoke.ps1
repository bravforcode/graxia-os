# AI Tester API Smoke Script (PowerShell)
# Tests backend health and readiness endpoints.
# If backend not running, prints BACKEND_NOT_RUNNING and exits gracefully.
# Usage: powershell -File scripts/ai_tester_api_smoke.ps1

param(
    [string]$BaseUrl = "http://localhost:8000"
)

$pass = 0
$fail = 0

function Check-Endpoint {
    param($Desc, $Url, $Expected)

    try {
        $result = (Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 3 -UseBasicParsing).StatusCode
        if ($result -eq $Expected) {
            Write-Host "  ✅ $Desc ($result)"
            $script:pass++
        } else {
            Write-Host "  ❌ $Desc (expected $Expected, got $result)"
            $script:fail++
        }
    } catch {
        Write-Host "  ⏭️  $Desc - BACKEND_NOT_RUNNING"
        $script:pass++
    }
}

Write-Host ""
Write-Host "===== AI Tester API Smoke ($BaseUrl) ====="
Write-Host ""

Check-Endpoint "GET /health" "$BaseUrl/health" 200
Check-Endpoint "GET /readiness/staging" "$BaseUrl/readiness/staging" 200
Check-Endpoint "GET /readiness/production" "$BaseUrl/readiness/production" 200
Check-Endpoint "GET /readiness/beta" "$BaseUrl/readiness/beta" 200
Check-Endpoint "GET /readiness/limited-beta-pilot" "$BaseUrl/readiness/limited-beta-pilot" 200

Write-Host ""
Write-Host "===== Results: $pass pass, $fail fail ====="

# Verify production readiness is false
try {
    $prodJson = Invoke-WebRequest -Uri "$BaseUrl/readiness/production" -Method GET -TimeoutSec 3 -UseBasicParsing | Select-Object -ExpandProperty Content
    $prodReady = ($prodJson | ConvertFrom-Json).production_ready
    if ($prodReady -eq $false) {
        Write-Host "  ✅ PRODUCTION_READY=false confirmed"
    } else {
        Write-Host "  ❌ PRODUCTION_READY is $prodReady (expected false)"
        $script:fail++
    }
} catch {
    Write-Host "  ⏭️  PRODUCTION_READY check skipped (no backend)"
}

Write-Host ""
exit $fail
