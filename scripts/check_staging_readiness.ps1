# ──────────────────────────────────────────────────────────────────────────────
# Graxia OS — Check Staging Readiness (PowerShell)
# Verifies all staging readiness requirements.
# ──────────────────────────────────────────────────────────────────────────────

param(
    [string]$BaseUrl = "http://localhost:8000"
)

$PASS = 0
$FAIL = 0

function Green { Write-Host "  ✅ $args" -ForegroundColor Green; $script:PASS++ }
function Red { Write-Host "  ❌ $args" -ForegroundColor Red; $script:FAIL++ }

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Graxia OS — Check Staging Readiness" -ForegroundColor Cyan
Write-Host "  Target: $BaseUrl" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$headers = @{"X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"}

# ── 1. Health Endpoint ───────────────────────────────────────────────────────
Write-Host "── 1. Health Endpoint ──────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health" -Headers $headers -UseBasicParsing
    $body = $resp.Content | ConvertFrom-Json
    if ($body.status -eq "ok") { Green "Health check returns ok" } else { Red "Health returned: $($body.status)" }
} catch { Red "Health endpoint unreachable" }

# ── 2. Readiness Endpoint ─────────────────────────────────────────────────────
Write-Host ""; Write-Host "── 2. Readiness Endpoint ───────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness" -Headers $headers -UseBasicParsing
    $body = $resp.Content | ConvertFrom-Json
    if ($body.production_ready -eq $false) { Green "Readiness confirms production_ready: false" } else { Red "production_ready not false" }
} catch { Red "Readiness endpoint unreachable" }

# ── 3. Local Agent Ready ────────────────────────────────────────────────────
Write-Host ""; Write-Host "── 3. Local Agent Readiness ─────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness/local-agent" -Headers $headers -UseBasicParsing
    $body = $resp.Content | ConvertFrom-Json
    if ($body.FULL_LOCAL_AGENT_READY -eq $true) { Green "Local agent is FULL_LOCAL_AGENT_READY" } else { Red "Local agent not fully ready" }
} catch { Red "Local agent readiness endpoint unreachable" }

# ── 4. Staging Readiness Reports Correctly ───────────────────────────────────
Write-Host ""; Write-Host "── 4. Staging Readiness ────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness/staging" -Headers $headers -UseBasicParsing
    $body = $resp.Content | ConvertFrom-Json
    if ($body.staging_ready -eq $false) { Green "Staging readiness shows staging_ready: false" } else { Red "Staging readiness incorrect" }
} catch { Red "Staging readiness endpoint unreachable" }

# ── 5. No Secrets in Responses ───────────────────────────────────────────────
Write-Host ""; Write-Host "── 5. No Secrets in Responses ────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health" -Headers $headers -UseBasicParsing
    $bodyStr = $resp.Content.ToLower()
    $secretKeys = @("secret", "password", "token", "key")
    $leaked = $false
    foreach ($k in $secretKeys) { if ($bodyStr -match $k) { $leaked = $true; break } }
    if (-not $leaked) { Green "Health response contains no secret-like keys" } else { Red "Potential secret leak detected in health response!" }
} catch { Red "Health endpoint unreachable" }

# ── 6. Database Connectivity ─────────────────────────────────────────────────
Write-Host ""; Write-Host "── 6. Database Connectivity ──────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health" -Headers $headers -UseBasicParsing
    $body = $resp.Content | ConvertFrom-Json
    if ($body.database) { Green "Health reports database status: $($body.database)" } else { Red "No database status in health" }
} catch { Red "Health endpoint unreachable" }

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""; Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Results: $PASS passed, $FAIL failed" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

if ($FAIL -gt 0) { exit 1 } else { Write-Host "  ✅ Staging readiness checks pass." -ForegroundColor Green }
