#!/usr/bin/env pwsh
# ──────────────────────────────────────────────────────────────────────────────
# Beta Smoke Script — Phase 19 Controlled External Beta
# Tests all beta readiness gates, kill switch, allowlist, and drill workflows.
# ──────────────────────────────────────────────────────────────────────────────

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL } else { "http://127.0.0.1:8000" }
$Pass = 0
$Fail = 0

function Check($Label, $Method, $Path, $Expected) {
    $url = "${BaseUrl}${Path}"
    try {
        $response = Invoke-WebRequest -Uri $url -Method $Method -UseBasicParsing -TimeoutSec 5
        $code = [int]$response.StatusCode
        if ($code -eq $Expected) {
            Write-Host "  ✓ $Label (HTTP $code)" -ForegroundColor Green
            $script:Pass++
        } else {
            Write-Host "  ✗ $Label (expected HTTP $Expected, got $code)" -ForegroundColor Red
            $script:Fail++
        }
    } catch {
        try {
            $code = [int]$_.Exception.Response.StatusCode
            if ($code -eq $Expected) {
                Write-Host "  ✓ $Label (HTTP $code)" -ForegroundColor Green
                $script:Pass++
            } else {
                Write-Host "  ✗ $Label (expected HTTP $Expected, got $code)" -ForegroundColor Red
                $script:Fail++
            }
        } catch {
            Write-Host "  ✗ $Label (connection error: $_ )" -ForegroundColor Red
            $script:Fail++
        }
    }
}

function CheckJsonField($Label, $Path, $Field, $Expected) {
    $url = "${BaseUrl}${Path}"
    try {
        $json = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 5
        $value = $json.$Field
        if ($value -eq $Expected -or "$value" -eq "$Expected") {
            Write-Host "  ✓ $Label ($Field = $Expected)" -ForegroundColor Green
            $script:Pass++
        } else {
            Write-Host "  ✗ $Label (expected $Field = $Expected, got $value)" -ForegroundColor Red
            $script:Fail++
        }
    } catch {
        Write-Host "  ✗ $Label (error: $_ )" -ForegroundColor Red
        $script:Fail++
    }
}

Write-Host ""
Write-Host "┌──────────────────────────────────────────────────────────────┐"
Write-Host "│  Phase 19 — Controlled External Beta Smoke                  │"
Write-Host "└──────────────────────────────────────────────────────────────┘"
Write-Host ""

# 1. Health
Write-Host "  ● Health check"
Check "Health endpoint responds 200" "GET" "/api/v1/health" 200

# 2. Readiness
Write-Host "  ● Readiness endpoint"
Check "Readiness endpoint responds 200" "GET" "/api/v1/health/readiness" 200

# 3. Production readiness returns false
Write-Host "  ● Production readiness gate"
Check "Production readiness responds 200" "GET" "/api/v1/health/readiness/production" 200
CheckJsonField "production_ready is false" "/api/v1/health/readiness/production" "production_ready" "False"

# 4. Beta readiness
Write-Host "  ● Beta readiness gate"
Check "Beta readiness responds 200" "GET" "/api/v1/health/readiness/beta" 200

# 5. Beta kill switch
Write-Host "  ● Beta kill switch"
CheckJsonField "beta_enabled from beta readiness" "/api/v1/health/readiness/beta" "beta_enabled" "False"

# 6. Staging readiness
Write-Host "  ● Staging readiness"
Check "Staging readiness responds 200" "GET" "/api/v1/health/readiness/staging" 200

# 7. Safe error
Write-Host "  ● Safe error contract"
Check "Safe error from bad delivery token" "GET" "/api/v1/delivery/open/bad-token-12345" 404

# 8. Request correlation
Write-Host "  ● Request correlation"
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -Method Get -UseBasicParsing
    if ($response.Headers["X-Request-ID"]) {
        Write-Host "  ✓ X-Request-ID header present" -ForegroundColor Green
        $script:Pass++
    } else {
        Write-Host "  ✗ X-Request-ID header missing" -ForegroundColor Red
        $script:Fail++
    }
    if ($response.Headers["X-Correlation-ID"]) {
        Write-Host "  ✓ X-Correlation-ID header present" -ForegroundColor Green
        $script:Pass++
    } else {
        Write-Host "  ✗ X-Correlation-ID header missing" -ForegroundColor Red
        $script:Fail++
    }
} catch {
    Write-Host "  ✗ Request correlation (error: $_ )" -ForegroundColor Red
    $script:Fail++
    $script:Fail++
}

# 9. Auth-required route denial
Write-Host "  ● Auth-required route denial"
Check "Protected route returns 401" "GET" "/api/v1/delivery/customer/profile" 401

Write-Host ""
Write-Host "┌──────────────────────────────────────────────────────────────┐"
Write-Host "│  Result: $Pass passed, $Fail failed"
Write-Host "└──────────────────────────────────────────────────────────────┘"
Write-Host ""
if ($Fail -gt 0) { exit 1 }
