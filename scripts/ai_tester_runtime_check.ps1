# Phase 22.5 — AI Tester Safe Runtime Check
# Usage: .\scripts\ai_tester_runtime_check.ps1

Write-Host "=== AI Tester Runtime Check ==="
Write-Host ""

try {
    $Response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "[Backend] Status: RUNNING (HTTP $($Response.StatusCode))"
} catch {
    Write-Host "[Backend] Status: NOT RUNNING"
}

try {
    $Response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "[Frontend] Status: RUNNING (HTTP $($Response.StatusCode))"
} catch {
    Write-Host "[Frontend] Status: NOT RUNNING"
}

try {
    $Response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/readiness/production" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "[Readiness] Production: $($Response.Content)"
} catch {
    Write-Host "[Readiness] BACKEND_NOT_RUNNING"
}

Write-Host ""
Write-Host "=== Check Complete ==="
