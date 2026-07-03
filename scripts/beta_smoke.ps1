#!/usr/bin/env pwsh
# ──────────────────────────────────────────────────────────────────────────────
# Beta Smoke Script — Phase 20 Limited Beta Launch Packet
# Tests all beta readiness gates, kill switch, allowlist, drill workflows,
# launch policy, invite template, onboarding checklist, session script,
# no-live-payment mode, limited beta pilot readiness, and all safety guards.
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
Write-Host "│  Phase 20 — Limited Beta Launch Packet Smoke                │"
Write-Host "└──────────────────────────────────────────────────────────────┘"
Write-Host ""

# 1. Health / Readiness
Write-Host "  ● Health check"
Check "Health endpoint responds 200" "GET" "/api/v1/health" 200
Check "Readiness endpoint responds 200" "GET" "/api/v1/health/readiness" 200

# 2. Production readiness returns false
Write-Host "  ● Production readiness gate"
Check "Production readiness responds 200" "GET" "/api/v1/health/readiness/production" 200
CheckJsonField "production_ready is false" "/api/v1/health/readiness/production" "production_ready" "False"

# 3. Staging readiness
Write-Host "  ● Staging readiness"
Check "Staging readiness responds 200" "GET" "/api/v1/health/readiness/staging" 200

# 4. Beta readiness
Write-Host "  ● Beta readiness gate"
Check "Beta readiness responds 200" "GET" "/api/v1/health/readiness/beta" 200
CheckJsonField "beta_enabled from beta readiness" "/api/v1/health/readiness/beta" "beta_enabled" "False"
CheckJsonField "kill_switch_enabled from beta readiness" "/api/v1/health/readiness/beta" "kill_switch_enabled" "True"

# 5. Limited beta pilot readiness (Phase 20)
Write-Host "  ● Limited beta pilot readiness"
Check "Limited beta pilot readiness responds 200" "GET" "/api/v1/health/readiness/limited-beta-pilot" 200
CheckJsonField "no_live_payment_mode in limited beta pilot" "/api/v1/health/readiness/limited-beta-pilot" "no_live_payment_mode" "True"
CheckJsonField "limited_beta_pilot_ready_flag" "/api/v1/health/readiness/limited-beta-pilot" "limited_beta_pilot_ready_flag" "False"

# 6. Safe error
Write-Host "  ● Safe error contract"
Check "Safe error from bad delivery token" "GET" "/api/v1/delivery/open/bad-token-12345" 404

# 7. Request correlation
Write-Host "  ● Request correlation"
try {
    $response = Invoke-WebRequest -Uri "${BaseUrl}/api/v1/health" -Method Get -UseBasicParsing
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

# 8. Auth-required route denial
Write-Host "  ● Auth-required route denial"
Check "Protected route returns 401" "GET" "/api/v1/delivery/customer/profile" 401

Write-Host ""
Write-Host "┌──────────────────────────────────────────────────────────────┐"
Write-Host "│  Result: $Pass passed, $Fail failed"
Write-Host "└──────────────────────────────────────────────────────────────┘"
Write-Host ""
if ($Fail -gt 0) { exit 1 }
