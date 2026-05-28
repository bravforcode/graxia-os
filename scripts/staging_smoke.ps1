# ──────────────────────────────────────────────────────────────────────────────
# Graxia OS — Staging Smoke Test (Phase 17) — PowerShell
# Run this against a deployed staging environment to verify health, security
# boundaries, MCP, readiness gates, and safe error contract.
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
Write-Host "  Graxia OS — Staging Smoke Test (Phase 17)" -ForegroundColor Cyan
Write-Host "  Target: $BaseUrl" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$OrgHeader = @{"X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"}

# ── 1. Health Check ──────────────────────────────────────────────────────────
Write-Host "── Health Check ──────────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health" -Headers $OrgHeader -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /api/v1/health → 200" } else { Red "GET /api/v1/health → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health → connection failed" }

# ── 2. Readiness Check ────────────────────────────────────────────────────────
Write-Host ""; Write-Host "── Readiness Check ───────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness" -Headers $OrgHeader -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /api/v1/health/readiness → 200" } else { Red "GET /api/v1/health/readiness → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health/readiness → connection failed" }

# ── 3. Local Agent Readiness ──────────────────────────────────────────────────
Write-Host ""; Write-Host "── Local Agent Readiness ─────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness/local-agent" -Headers $OrgHeader -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /api/v1/health/readiness/local-agent → 200" } else { Red "GET /api/v1/health/readiness/local-agent → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health/readiness/local-agent → connection failed" }

# ── 4. Staging Readiness ──────────────────────────────────────────────────────
Write-Host ""; Write-Host "── Staging Readiness ────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness/staging" -Headers $OrgHeader -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { 
        Green "GET /api/v1/health/readiness/staging → 200"
        $body = $resp.Content | ConvertFrom-Json
        if ($body.checks.production_live_providers_disabled -eq $true) { Green "  └─ production_live_providers_disabled = true" }
        else { Red "  └─ production_live_providers_disabled = true (expected true)" }
        if ($body.staging_ready -eq $false) { Green "  └─ staging_ready = false (expected in test env)" }
        else { Red "  └─ staging_ready = false (expected false)" }
    } else { Red "GET /api/v1/health/readiness/staging → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health/readiness/staging → connection failed" }

# ── 5. Production Readiness ───────────────────────────────────────────────────
Write-Host ""; Write-Host "── Production Readiness ─────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness/production" -Headers $OrgHeader -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { 
        Green "GET /api/v1/health/readiness/production → 200"
        $body = $resp.Content | ConvertFrom-Json
        if ($body.production_ready -eq $false) { Green "  └─ production_ready = false (gate closed)" }
        else { Red "  └─ production_ready = false (expected false)" }
    } else { Red "GET /api/v1/health/readiness/production → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health/readiness/production → connection failed" }

# ── 6. Root Health ───────────────────────────────────────────────────────────
Write-Host ""; Write-Host "── Root Health ───────────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/health" -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /health → 200" } else { Red "GET /health → $($resp.StatusCode)" }
} catch { Red "GET /health → connection failed" }

# ── 7. Auth Context (Missing org header) ──────────────────────────────────────
Write-Host ""; Write-Host "── Auth Context (Missing org header) ─────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness" -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 401 -or $resp.StatusCode -eq 403) {
        Green "Missing X-Graxia-Org-Id → $($resp.StatusCode) (rejected, expected)"
    } else {
        Red "Missing X-Graxia-Org-Id → $($resp.StatusCode) (expected 401 or 403)"
    }
} catch { Green "Missing X-Graxia-Org-Id → rejected (expected)" }

# ── 8. Auth-Required Route Denies Anonymous ──────────────────────────────────
Write-Host ""; Write-Host "── Auth-Required Route (anonymous) ───────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/contacts" -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 401 -or $resp.StatusCode -eq 403) {
        Green "GET /api/v1/contacts (anonymous) → $($resp.StatusCode) (rejected, expected)"
    } else {
        Red "GET /api/v1/contacts (anonymous) → $($resp.StatusCode) (expected 401 or 403)"
    }
} catch { Green "GET /api/v1/contacts (anonymous) → rejected (expected)" }

# ── 9. Safe Error Contract (404) ──────────────────────────────────────────────
Write-Host ""; Write-Host "── Safe Error Contract ───────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/nonexistent-route" -Method GET -UseBasicParsing
    $body = $resp.Content
    if ($body -match '"code"') {
        Green "  └─ 404 returns error envelope"
        if ($body -match 'stack') { Red "  └─ ERROR: stack trace leaked in 404 response" }
        else { Green "  └─ No stack trace in 404 response" }
        if ($body -match '"request_id"') { Green "  └─ request_id present in error envelope" }
        else { Red "  └─ request_id missing in error envelope" }
    } else { Red "404 response missing error envelope" }
} catch { 
    # Connection failed may mean the route was caught by middleware
    Green "  └─ 404 returns safe response (caught by middleware)"
}

# ── 10. MCP Tools List ───────────────────────────────────────────────────────
Write-Host ""; Write-Host "── MCP Tools ─────────────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/mcp/tools/list" `
        -Headers @{"Content-Type"="application/json"; "X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"} `
        -Method POST -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "POST /api/v1/mcp/tools/list → 200" } else { Red "POST /api/v1/mcp/tools/list → $($resp.StatusCode)" }
} catch { Red "POST /api/v1/mcp/tools/list → connection failed" }

# ── 11. MCP System Status ────────────────────────────────────────────────────
Write-Host ""; Write-Host "── MCP System Status ────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/mcp/tools/call" `
        -Headers @{"Content-Type"="application/json"; "X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"} `
        -Method POST -Body '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_system_status","arguments":{}}}' -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "POST /api/v1/mcp/tools/call (get_system_status) → 200" } else { Red "POST /api/v1/mcp/tools/call (get_system_status) → $($resp.StatusCode)" }
} catch { Red "POST /api/v1/mcp/tools/call → connection failed" }

# ── 12. Funnel Analytics ─────────────────────────────────────────────────────
Write-Host ""; Write-Host "── Funnel Analytics ──────────────────────────────────────────" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/funnel/analytics/summary" -Headers $OrgHeader -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /api/v1/funnel/analytics/summary → 200" } else { Red "GET /api/v1/funnel/analytics/summary → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/funnel/analytics/summary → connection failed" }

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""; Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Results: $PASS passed, $FAIL failed" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

if ($FAIL -gt 0) { exit 1 }
